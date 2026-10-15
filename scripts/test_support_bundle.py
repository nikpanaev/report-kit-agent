"""Synthetic support data, crash persistence and offline fallback; never real user state."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch
import uuid
import zipfile

import support_bundle as support
import test_prepare_release as release_fixture
from check_package import check as package_check, identity


class SupportBundle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='report-kit-support-test-');self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name).resolve();self.state=self.base/'state'
        self.env=patch.dict(os.environ,{'REPORT_SKILLS_STATE_DIR':str(self.state)});self.env.start();self.addCleanup(self.env.stop)
        def receipt():
            print(json.dumps({'test':self.id(),'result':'Synthetic files inspected by assertions; see unittest outcome',
                'temporary_files':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.base.rglob('*') if p.is_file() and not p.is_symlink()]}))
        self.addCleanup(receipt)

    def contents(self,path):
        with zipfile.ZipFile(path) as z:
            self.assertEqual(set(z.namelist()),{'ПРОЧИТАЙТЕ.txt','events.json','environment.json','manifest.json'})
            return {name:z.read(name).decode('utf-8') for name in z.namelist()}

    def test_failure_sequence_recovery_and_unknown_result(self):
        op=support.emit('livedune','api','started')
        support.emit('livedune','api','finished','unknown','ACTION_UNCERTAIN',operation=op)
        support.emit('livedune','recovery','recovery','success')
        op2=support.emit('ui','capture','started')
        support.emit('ui','capture','retry','failure','TIMEOUT',operation=op2)
        support.emit('ui','capture','finished','failure','TIMEOUT',operation=op2)
        files=self.contents(support.bundle());events=json.loads(files['events.json'])
        self.assertEqual([e['kind'] for e in events],['started','finished','recovery','started','retry','finished'])
        self.assertEqual(events[0]['operation'],events[1]['operation'])
        self.assertNotEqual(events[0]['operation'],op)
        self.assertEqual(events[1]['result'],'unknown')
        self.assertIn('истекло время ожидания',files['ПРОЧИТАЙТЕ.txt'])
        self.assertIn('успешно',files['ПРОЧИТАЙТЕ.txt'])
        second=json.loads(self.contents(support.bundle())['events.json'])
        self.assertNotEqual(events[0]['run'],second[0]['run'])

    def test_no_private_data_even_in_errors_unknown_fields_or_program_versions(self):
        banned=['CANARY_CLIENT_NAME','CANARY_EMPLOYEE_NAME','CANARY_SECRET_KEY','CANARY_SESSION_COOKIE',
            'person@example.test','+000000000000','/'+'Users/private-person/Documents/client.csv',
            'https://docs.google.com/'+'document/d/PRIVATE_DOC_ID','CANARY_COMPUTER','CANARY_DEVICE_ID','CANARY_DIALOG_TEXT']
        payload=' | '.join(banned)
        op=support.emit(payload,payload,'check','failure',payload,program_versions={'node':payload,'unknown-program':payload})
        root=support.store();path=next((root/'events').glob('e-*.json'))
        raw=json.loads(path.read_text(encoding='utf-8'));raw.update(message=payload,stdout=payload,stderr=payload,response=payload,
            client=payload,hostname=payload,username=payload,device=payload)
        path.write_text(json.dumps(raw),encoding='utf-8')
        for value in self.contents(support.bundle()).values():
            for canary in banned:self.assertNotIn(canary,value)
        self.assertEqual(support.error_code(TimeoutError(payload)),'TIMEOUT')
        events=json.loads(self.contents(support.bundle())['events.json'])
        self.assertEqual(events[0]['component'],'unknown');self.assertEqual(events[0]['error'],'UNKNOWN')
        self.assertNotIn('message',events[0]);self.assertTrue(support.identifier(op))

    def test_survives_abrupt_process_exit_and_flags_unfinished(self):
        script='import sys,os;sys.path.insert(0,sys.argv[1]);import support_bundle as s;s.emit("ui","capture","started");os._exit(9)'
        r=subprocess.run([sys.executable,'-B','-c',script,str(Path(support.__file__).parent)],env=os.environ.copy(),capture_output=True)
        self.assertEqual(r.returncode,9)
        data=self.contents(support.bundle());self.assertEqual(json.loads(data['manifest.json'])['unfinished_operations'],1)
        self.assertIn('ещё выполняющееся',data['ПРОЧИТАЙТЕ.txt'])

    def test_partial_corrupt_oversized_invalid_and_future_records_are_excluded(self):
        support.emit('agent','validation','check','failure','CORRUPT_DATA');root=support.store()
        one=json.loads(next((root/'events').glob('e-*.json')).read_text(encoding='utf-8'))
        for raw in [b'{"half":',b'\xff\xfe',b'x'*5000,b'null',b'['*1100+b']'*1100]:
            (root/'events'/('e-'+str(uuid.uuid4())+'.json')).write_bytes(raw)
        one['at']='2999-01-01T00:00:00Z';(root/'events'/('e-'+str(uuid.uuid4())+'.json')).write_text(json.dumps(one),encoding='utf-8')
        data=self.contents(support.bundle());self.assertEqual(len(json.loads(data['events.json'])),1)
        self.assertEqual(json.loads(data['manifest.json'])['excluded_records'],6)
        self.assertIn('Исключено',data['ПРОЧИТАЙТЕ.txt'])

    def test_empty_store_does_not_claim_complete_diagnostics(self):
        data=self.contents(support.bundle());self.assertEqual(json.loads(data['events.json']),[])
        self.assertIn('Служебные сведения не сохранились',data['ПРОЧИТАЙТЕ.txt'])
        self.assertIn('не гарантирует полноту',data['ПРОЧИТАЙТЕ.txt'])

    def test_returned_bundle_survives_clock_correction_and_keeps_limit(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
        for _ in range(support.POLICY['bundle_limit']):
            path = support.bundle(); os.utime(path, (future, future))
        path = support.bundle()
        self.contents(path)
        self.assertEqual(len(support.owned_files(support.store(), 'bundles')), support.POLICY['bundle_limit'])

    @unittest.skipIf(sys.platform == 'win32', 'Native macOS/POSIX launcher; Windows is a separate employee check')
    def test_fallback_ignores_unrelated_python_environment(self):
        destination = support.prepare_fallback(self.base / 'fallback', self.state, python=Path(sys.executable))
        stub = self.base / 'bin'; stub.mkdir()
        (stub / 'open').write_text('#!/bin/sh\nexit 0\n', encoding='utf-8'); (stub / 'open').chmod(0o700)
        environment = os.environ.copy(); environment.update(PYTHONHOME=str(self.base / 'missing-home'),
            PYTHONPATH=str(self.base / 'unrelated'), PATH=str(stub)+os.pathsep+environment['PATH'])
        run = subprocess.run(['/bin/sh', str(destination / 'Подготовить файл поддержки.command')],
            env=environment, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, 'Isolated collector must start without the unrelated Python configuration')
        archives = support.owned_files(support.store(), 'bundles'); self.assertEqual(len(archives), 1)
        self.contents(archives[0])

    def test_retention_count_age_bytes_and_bundles_only_own_files(self):
        root=support.store();now=datetime.now(timezone.utc)
        raw=root/'events/requests.jsonl';raw.write_bytes(b'private API accounting must stay')
        foreign=root/'events/customer.csv';foreign.write_bytes(b'original source')
        with patch.dict(support.POLICY,{'event_limit':2,'event_bytes_limit':1000000,'bundle_limit':2}):
            for _ in range(5):support.emit('agent','validation','check','success')
            self.assertEqual(len(support.owned_files(root,'events')),2)
            old=support.owned_files(root,'events')[0];os.utime(old,((now-timedelta(days=20)).timestamp(),)*2)
            support.prune(root,now);self.assertFalse(old.exists())
            with patch.dict(support.POLICY,{'event_bytes_limit':10}):support.prune(root)
            self.assertEqual(len(support.owned_files(root,'events')),0)
            for _ in range(4):support.bundle()
            self.assertEqual(len(support.owned_files(root,'bundles')),2)
            old=support.owned_files(root,'bundles')[0];os.utime(old,((now-timedelta(days=8)).timestamp(),)*2)
            support.prune(root,now);self.assertFalse(old.exists())
        self.assertEqual(raw.read_bytes(),b'private API accounting must stay');self.assertEqual(foreign.read_bytes(),b'original source')

    def test_archive_limit_failure_removes_only_its_new_archive(self):
        support.emit('agent','validation','check','success');root=support.store()
        with patch.dict(support.POLICY,{'bundle_max_bytes':1}):
            with self.assertRaisesRegex(ValueError,'BUNDLE_SIZE_LIMIT'):support.bundle()
        self.assertFalse(support.owned_files(root,'bundles'))
        self.assertEqual(len(support.owned_files(root,'events')),1)

    def test_symlink_and_foreign_store_are_never_followed_or_overwritten(self):
        foreign=self.base/'foreign';foreign.mkdir();secret=foreign/'secret';secret.write_text('CANARY_PRIVATE',encoding='utf-8')
        self.state.mkdir();(self.state/'support-v1').symlink_to(foreign,target_is_directory=True)
        with self.assertRaises(ValueError):support.bundle()
        self.assertEqual(secret.read_text(encoding='utf-8'),'CANARY_PRIVATE')
        (self.state/'support-v1').unlink();root=self.state/'support-v1';root.mkdir();(root/'foreign').write_text('keep',encoding='utf-8')
        with self.assertRaises(ValueError):support.bundle()
        self.assertEqual((root/'foreign').read_text(encoding='utf-8'),'keep')

    def test_fallback_collects_without_running_agent_or_skill_installation(self):
        support.emit('agent','setup','check','failure','MISSING_TOOL')
        folder=support.prepare_fallback(self.base/'Поддержка Report Kit',self.state)
        self.assertEqual((folder/'scripts/support_bundle.py').read_bytes(),Path(support.__file__).read_bytes())
        command=[sys.executable,'-B',str(folder/'scripts/support_bundle.py'),'--saved-state']
        r=subprocess.run(command,env={**os.environ,'PATH':'','REPORT_SKILLS_STATE_DIR':str(self.base/'wrong')},capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr);self.assertIn('Файл для поддержки готов',r.stdout)
        archives=support.owned_files(support.store(),'bundles');self.assertEqual(len(archives),1)
        self.assertEqual(json.loads(self.contents(archives[0])['events.json'])[0]['error'],'MISSING_TOOL')
        with self.assertRaises(ValueError):support.prepare_fallback(folder,self.state)
        self.assertIn('Подготовить файл поддержки.command',{p.name for p in folder.iterdir()})

    def test_windows_launcher_is_prepared_without_claiming_windows_execution(self):
        with patch.object(sys,'platform','win32'):
            folder=support.prepare_fallback(self.base/'windows-fixture',self.state)
        content=(folder/'Подготовить файл поддержки.cmd').read_text(encoding='utf-8')
        self.assertIn('--saved-state --open-folder',content);self.assertNotIn('ExecutionPolicy',content)
        root=Path(support.__file__).resolve().parents[1]
        self.assertEqual((root/'Подготовить файл поддержки.cmd').read_text(encoding='utf-8'),support.WINDOWS_LAUNCHER)
        self.assertEqual((root/'Подготовить файл поддержки.command').read_text(encoding='utf-8'),support.MAC_LAUNCHER)

    def test_failed_event_write_does_not_change_business_failure(self):
        with patch.object(support,'store',side_effect=PermissionError('CANARY_SECRET')):
            op=support.emit('agent','validation','check','failure','ACCESS_DENIED')
        self.assertTrue(support.identifier(op))

    def test_collector_pair_mirror_is_enforced_without_executing_either_copy(self):
        f=release_fixture.Releases('runTest');f.setUp();self.addCleanup(f.doCleanups)
        for root,prefix in [(f.agent,'scripts'),(f.skills,'skills/_shared')]:
            for name,text in [('support_bundle.py' if root==f.agent else 'support_events.py','inert fixture'),('support-policy.json','{}')]:
                path=root/prefix/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
            inventory=root/'PUBLIC-FILES.json';d=json.loads(inventory.read_text(encoding='utf-8'))
            d['files'] += [prefix+'/'+('support_bundle.py' if root==f.agent else 'support_events.py'),prefix+'/support-policy.json']
            inventory.write_text(json.dumps(d),encoding='utf-8')
        dep=f.agent/'dependencies.json';d=json.loads(dep.read_text(encoding='utf-8'));d['report-kit-skills']['package_sha256']=identity(f.skills);dep.write_text(json.dumps(d),encoding='utf-8')
        self.assertEqual(package_check(f.agent,f.skills)['status'],'PASS_LIMITED')
        (f.agent/'scripts/support_bundle.py').write_text('different inert fixture',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'support_collector_drift'):package_check(f.agent,f.skills)

    def test_cli_update_failure_projects_only_safe_status_and_not_the_input(self):
        source=self.base/'source.json';source.write_text('{"CANARY_PRIVATE_FIELD":"CANARY_PRIVATE_VALUE"}',encoding='utf-8')
        r=subprocess.run([sys.executable,'-B',str(Path(support.__file__).with_name('updates.py')),'due',str(source)],
                         capture_output=True,text=True,env=os.environ.copy())
        self.assertEqual(r.returncode,1)
        values=self.contents(support.bundle());text=''.join(values.values())
        self.assertNotIn('CANARY_PRIVATE',text)
        events=json.loads(values['events.json']);self.assertEqual(events[-1]['component'],'updates');self.assertEqual(events[-1]['result'],'failure')

    def test_broken_product_metadata_does_not_prevent_archive(self):
        broken=self.base/'broken-product';broken.mkdir();(broken/'plugin.json').write_text('{half',encoding='utf-8')
        with patch.object(support,'PACKAGE',broken):
            support.emit('setup','setup','check','failure','CORRUPT_DATA')
            files=self.contents(support.bundle())
        self.assertEqual(set(json.loads(files['environment.json'])['collector_versions']),{'python'})
        self.assertEqual(len(json.loads(files['events.json'])),1)

    def test_concurrent_writers_keep_independent_events_during_expiry(self):
        root=support.store()
        for _ in range(5):
            support.emit('ui','queue','check','success')
        old=(datetime.now(timezone.utc)-timedelta(days=20)).timestamp()
        for p in support.owned_files(root,'events'):os.utime(p,(old,old))
        code='import sys;sys.path.insert(0,sys.argv[1]);import support_bundle as s;[s.emit("ui","queue","check","success") for _ in range(10)]'
        children=[subprocess.Popen([sys.executable,'-B','-c',code,str(Path(support.__file__).parent)],env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(3)]
        for child in children:
            stdout,stderr=child.communicate(timeout=20);self.assertEqual(child.returncode,0);self.assertNotIn(b'EVENT_NOT_SAVED',stderr)
        rows=json.loads(self.contents(support.bundle())['events.json']);self.assertEqual(len(rows),30)

    def test_archive_collision_never_removes_the_preexisting_file(self):
        root=support.store();now=datetime.now(timezone.utc);fixed=uuid.uuid4()
        existing=root/'bundles'/('Report-Kit-support-'+now.strftime('%Y%m%d')+'-'+str(fixed)+'.zip')
        existing.write_bytes(b'preexisting owned archive')
        with patch.object(support.uuid,'uuid4',return_value=fixed):
            with self.assertRaises(FileExistsError):support.bundle(now=now)
        self.assertEqual(existing.read_bytes(),b'preexisting owned archive')

    def test_fallback_inside_workspace_can_read_its_sibling_support_store(self):
        folder=support.prepare_fallback(self.state/'Поддержка Report Kit',self.state)
        r=subprocess.run([sys.executable,'-B',str(folder/'scripts/support_bundle.py'),'--saved-state'],
                         env=os.environ.copy(),capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(len(support.owned_files(support.store(),'bundles')),1)

    def test_store_still_refuses_overlap_with_package_code(self):
        package=self.base/'source-package'
        with patch.object(support,'PACKAGE',package):
            with self.assertRaisesRegex(ValueError,'SUPPORT_PATH_BOUNDARY'):support.store(package)
        self.assertFalse(package.exists())
        with patch.object(support,'PACKAGE',self.base/'support-v1/source-package'):
            with self.assertRaisesRegex(ValueError,'SUPPORT_PATH_BOUNDARY'):support.store(self.base)

    def test_uri_and_unc_state_locations_stop_before_filesystem_access(self):
        with patch.object(Path,'resolve',side_effect=AssertionError('Must not reach remote filesystem')):
            for value in ['https://example.invalid/support','//server/share','\\\\server\\share']:
                with self.assertRaisesRegex(ValueError,'LOCAL_SUPPORT_PATH_REQUIRED'):support.store(value)

    def test_python_and_node_timestamp_precision_preserves_event_order(self):
        op=support.emit('livedune','api','started');support.emit('livedune','api','finished','success',operation=op)
        paths=support.owned_files(support.store(),'events');prefix=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
        for path in paths:
            value=json.loads(path.read_text(encoding='utf-8'));value['at']=prefix+('.123Z' if value['kind']=='started' else '.123456Z');path.write_text(json.dumps(value),encoding='utf-8')
        files=self.contents(support.bundle());events=json.loads(files['events.json'])
        self.assertEqual([e['kind'] for e in events],['started','finished'])
        self.assertEqual(json.loads(files['manifest.json'])['unfinished_operations'],0)

    @unittest.skipUnless(sys.platform=='darwin','Actual macOS shell wrapper; not a Windows claim')
    def test_clickable_mac_wrapper_collects_without_agent_with_folder_open_isolated(self):
        folder=support.prepare_fallback(self.state/'Поддержка Report Kit',self.state)
        tools=self.base/'bin';tools.mkdir();(tools/'python3').symlink_to(sys.executable)
        opener=tools/'open';opener.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$REPORT_KIT_TEST_OPEN_LOG"\n',encoding='utf-8');opener.chmod(0o700)
        observed=self.base/'opened.txt'
        env={**os.environ,'PATH':str(tools)+':/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','REPORT_KIT_TEST_OPEN_LOG':str(observed)}
        r=subprocess.run(['/bin/sh',str(folder/'Подготовить файл поддержки.command')],cwd=self.base,env=env,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        archive=support.owned_files(support.store(),'bundles')[0]
        self.assertIn(str(archive),observed.read_text(encoding='utf-8'))
        self.assertEqual(len(self.contents(archive)),4)


if __name__=='__main__':unittest.main()
