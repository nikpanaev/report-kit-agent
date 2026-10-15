"""Isolated first-setup and update paths. Native host/download observations are synthetic."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch
import subprocess
import sys

import test_updates
import updates


class SingleEntry(unittest.TestCase):
    def setUp(self):
        self.f = test_updates.Updates('runTest'); self.f.setUp(); self.addCleanup(self.f.doCleanups)
        def receipt():
            print(json.dumps({'test':self.id(),'result':'Synthetic fixture inspected by assertions; see unittest result',
                'temporary_files':[{'path':str(p),'sha256':updates.identity_file(p)} for p in self.f.base.rglob('*') if p.is_file()]}))
        self.addCleanup(receipt)
        self.source = self.f.source
        self.roots = {'report-kit-agent': self.f.candidate_agent, 'report-kit-skills': self.f.candidate_skills}
        for name, root in self.roots.items():
            path = root / 'skills' / ('setup' if name.endswith('agent') else 'vk-post-screenshot') / 'SKILL.md'
            path.parent.mkdir(parents=True)
            path.write_text('---\nname: '+path.parent.name+'\ndescription: "Synthetic fixture"\n---\n', encoding='utf-8')
            if name.endswith('skills'):
                p = root / 'skills/vk-comment-screenshot/SKILL.md'; p.parent.mkdir()
                p.write_text('---\nname: vk-comment-screenshot\ndescription: "Synthetic fixture"\n---\n', encoding='utf-8')
            p = root / '.agents/plugins/marketplace.json'; p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'plugins':[{'name':name,'source':{'source':'local','path':'./'}}]}), encoding='utf-8')
            self.inventory(root)
        for name,root in [('report-kit-agent',self.f.current_agent),('report-kit-skills',self.f.current_skills)]:
            p=root/'.agents/plugins/marketplace.json';p.parent.mkdir(parents=True)
            p.write_text(json.dumps({'plugins':[{'name':name,'source':{'source':'local','path':'./'}}]}),encoding='utf-8')
            self.inventory(root)
        self.f.old=self.f.pair(self.f.current_agent,self.f.current_skills)
        settings=json.loads((self.f.workspace/'settings.json').read_text(encoding='utf-8'));settings['packages']=self.f.old;self.f.write('settings.json',settings)
        dep = self.f.candidate_agent/'dependencies.json'
        dep.write_text(json.dumps({'report-kit-skills':self.f.pair(*self.roots.values())['report-kit-skills']}), encoding='utf-8')
        self.inventory(self.f.candidate_agent)
        self.f.new = self.f.pair(*self.roots.values()); self.f.release['packages'] = self.f.new
        for record in self.f.compatibility['clients'].values():
            p = self.f.workspace / record['regression_receipt']
            d = json.loads(p.read_text(encoding='utf-8')); d['candidate'] = self.f.new
            p.write_text(json.dumps(d), encoding='utf-8'); record['regression_sha256'] = updates.identity_file(p)
        self.f.write('compatibility.json',self.f.compatibility)
        self.delivery = {'schema_version':1,'release':self.f.release,'assets':{}}
        self.observed = {}; self.downloads = {}
        for name, root in self.roots.items():
            raw = self.archive(root); p = self.f.base/(name+'.tar'); p.write_bytes(raw); self.downloads[name] = p
            repo = self.source['agent_repository' if name.endswith('agent') else 'skills_repository']
            tag = 'v'+self.f.new[name]['version']; url = repo+'/releases/download/'+tag+'/'+name+'-'+self.f.new[name]['version']+'.tar'
            self.delivery['assets'][name] = {'repository':repo,'tag':tag,'commit':'1'*40,'url':url,'size':len(raw),'archive_sha256':hashlib.sha256(raw).hexdigest()}
            self.observed[name] = {'repository':repo,'tag':tag,'commit':'1'*40,'asset_url':url,'draft':False,'published':True,'prerelease':False,'source_kind':'native_tool_result','source_locator':'synthetic release observation'}

    @staticmethod
    def inventory(root):
        paths = [p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()]
        (root/'PUBLIC-FILES.json').write_text(json.dumps({'schema_version':1,'files':sorted(paths)}),encoding='utf-8')

    @staticmethod
    def archive(root):
        out=io.BytesIO()
        with tarfile.open(fileobj=out,mode='w') as tar:
            for p in sorted(root.rglob('*')):
                if p.is_file():
                    raw=p.read_bytes(); item=tarfile.TarInfo(p.relative_to(root).as_posix()); item.size=len(raw); tar.addfile(item,io.BytesIO(raw))
        return out.getvalue()

    def stage(self):
        return updates.stage_candidate(self.source,self.delivery,self.observed,self.downloads,self.f.base/'stage',list(self.roots.values())+[self.f.workspace])

    def host(self):
        return {'checked_at':'2026-10-14T10:00:00Z','source_kind':'native_tool_result','source_locator':'synthetic host',
                'required_skills':['vk-comment-screenshot'],'tool_checks':{'Python':'PASS'},'new_permissions':[],
                'namespace_conflicts':[],'active_runs':[],'runs_inventory_complete':True,'approval':'not_required'}

    def test_clean_setup_uses_published_pair_and_same_preflight(self):
        selected=updates.select_release({'schema_version':1,'releases':[self.f.release]},self.source,None)
        self.assertEqual(selected,self.f.release)
        staged=self.stage(); self.assertEqual(staged['status'],'STAGED_NOT_INSTALLED')
        result=updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)
        self.assertEqual(result['clients_checked'],2)

    def test_same_pair_repairs_missing_skills_and_foreign_version_is_untouched(self):
        self.f.current_agent=self.f.candidate_agent
        settings=json.loads((self.f.workspace/'settings.json').read_text(encoding='utf-8')); settings['packages']=self.f.new; self.f.write('settings.json',settings)
        before=self.f.current_skills.joinpath('VERSION').read_bytes()
        result=updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)
        self.assertEqual(result['candidate'],self.f.new)
        self.assertEqual(self.f.current_skills.joinpath('VERSION').read_bytes(),before)

    def test_compatible_installed_pair_needs_no_new_release(self):
        self.assertIsNone(updates.select_release({'schema_version':1,'releases':[self.f.release]},self.source,self.f.new))

    def test_no_published_release_or_draft_or_wrong_origin(self):
        d=copy.deepcopy(self.f.release); d['published']=False
        self.assertIsNone(updates.select_release({'schema_version':1,'releases':[d]},self.source,None))
        for key,value in [('repository','https://github.com/other/other'),('draft',True),('published',False),('commit','2'*40),('asset_url','https://elsewhere.invalid/file')]:
            with self.subTest(key=key):
                obs=copy.deepcopy(self.observed); obs['report-kit-skills'][key]=value
                with self.assertRaises(ValueError): updates.delivery_check(self.source,self.delivery,obs)

    def test_damaged_or_interrupted_download_never_creates_stage(self):
        p=self.downloads['report-kit-skills']; raw=p.read_bytes()
        for bad in [raw[:-100],bytes([raw[0]^1])+raw[1:]]:
            p.write_bytes(bad)
            with self.assertRaisesRegex(ValueError,'download_'):self.stage()
            self.assertFalse((self.f.base/'stage').exists())

    def test_archive_escape_link_case_collision_and_executable_are_not_run(self):
        p=self.downloads['report-kit-skills']
        for kind in ['escape','link','case']:
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w') as tar:
                item=tarfile.TarInfo('../escape' if kind=='escape' else 'safe')
                if kind=='link':item.type=tarfile.SYMTYPE; item.linkname='/tmp/escape'
                tar.addfile(item)
                if kind=='case':tar.addfile(tarfile.TarInfo('SAFE'))
            raw=out.getvalue(); p.write_bytes(raw)
            a=self.delivery['assets']['report-kit-skills']; a.update(size=len(raw),archive_sha256=hashlib.sha256(raw).hexdigest())
            with self.assertRaises(ValueError):self.stage()
            self.assertFalse((self.f.base/'stage').exists())

    def test_existing_stage_and_client_files_preserved(self):
        stage=self.f.base/'stage'; stage.mkdir(); marker=stage/'keep'; marker.write_bytes(b'foreign')
        with self.assertRaises(ValueError):self.stage()
        self.assertEqual(marker.read_bytes(),b'foreign')

    def test_missing_tools_permission_conflict_active_and_unknown_runs(self):
        plan=self.f.preflight(); h=self.host()
        for key,value,status in [('tool_checks',{},'NEEDS_TOOLS'),('tool_checks',{'Python':'DENIED'},'NEEDS_TOOLS'),('new_permissions',['browser.read'],'NEEDS_PERMISSION'),('namespace_conflicts',['foreign-vk'],'KEEP_FOREIGN_SKILLS'),('active_runs',['report-1'],'DEFER_UNTIL_IDLE'),('runs_inventory_complete',False,'CHECK_RUNNING_WORK'),('approval','unavailable','MANUAL_HOST_STEP')]:
            with self.subTest(key=key):
                host=copy.deepcopy(h);host[key]=value
                result=updates.installation_plan(plan,self.f.compatibility,self.f.candidate_skills,host,'2026-10-14T10:05:00Z')
                self.assertEqual(result['status'],status)
        self.assertEqual(updates.installation_plan(plan,self.f.compatibility,self.f.candidate_skills,h,'2026-10-14T10:05:00Z')['status'],'CHECK_CONSENT')

    def test_incompatible_existing_client_blocks_even_bootstrap(self):
        self.f.compatibility['clients']['second']['interfaces']['profile']=42;self.f.write('compatibility.json',self.f.compatibility)
        with self.assertRaisesRegex(ValueError,'interface_incompatible'):
            updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)

    def test_offline_first_setup_differs_from_offline_installed(self):
        self.assertEqual(updates.setup_status(False,False)['status'],'NEEDS_CONNECTION')
        self.assertEqual(updates.setup_status(False,True)['status'],'KEEP_VERIFIED_CURRENT')
        self.assertFalse(updates.setup_status(False,True)['notify'])

    def test_failed_activation_selects_saved_pair_without_reverting_client_bytes(self):
        plan=self.f.preflight(); before={p:p.read_bytes() for p in self.f.workspace.rglob('*') if p.is_file()}
        saved={'packages':self.f.old,'verified':True,'source_locator':'synthetic native backup'}
        result=updates.activation_result(plan,saved,self.f.new,False)
        self.assertEqual(result['status'],'ROLLBACK_REQUIRED');self.assertEqual(result['selected'],self.f.old)
        self.assertEqual(before,{p:p.read_bytes() for p in self.f.workspace.rglob('*') if p.is_file()})
        self.assertEqual(updates.activation_result(plan,saved,self.f.new,True)['status'],'VERIFY_CLIENT_REFRESH')
        self.assertEqual(updates.activation_result(plan,saved,None,False)['status'],'ROLLBACK_REQUIRED')
        saved['verified']=False
        with self.assertRaises(ValueError):updates.activation_result(plan,saved,self.f.new,False)

    def test_clean_zero_client_inventory_and_downloaded_code_never_runs(self):
        settings=json.loads((self.f.workspace/'settings.json').read_text(encoding='utf-8'))
        settings['clients']=[];self.f.write('settings.json',settings)
        for p in (self.f.workspace/'clients').glob('*/AGENT.md'):p.unlink()
        self.f.compatibility['clients']={};self.f.write('compatibility.json',self.f.compatibility)
        result=updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)
        self.assertEqual(result['clients_checked'],0)
        # Even a syntactically invalid script is inert data during download/staging.
        root=self.f.candidate_skills;p=root/'never_run.py';p.write_bytes(b'not executable Python !!!')
        self.inventory(root); dep=self.f.candidate_agent/'dependencies.json'
        d=json.loads(dep.read_text(encoding='utf-8'));d['report-kit-skills']=self.f.pair(*self.roots.values())['report-kit-skills'];dep.write_text(json.dumps(d),encoding='utf-8')
        self.delivery['release']['packages']=self.f.pair(*self.roots.values())
        for name,r in self.roots.items():
            raw=self.archive(r);self.downloads[name].write_bytes(raw);a=self.delivery['assets'][name]
            a.update(size=len(raw),archive_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.stage()['status'],'STAGED_NOT_INSTALLED')
        self.assertEqual((self.f.base/'stage/report-kit-skills/never_run.py').stat().st_mode & 0o111,0)

    def test_agent_only_and_pair_release_selection(self):
        for skills in [self.f.old['report-kit-skills'],self.f.new['report-kit-skills']]:
            r=copy.deepcopy(self.f.release);r['packages']['report-kit-skills']=skills
            self.assertEqual(updates.select_release({'schema_version':1,'releases':[r]},self.source,self.f.old),r)

    def test_new_execution_hook_blocks_compatible_auto_path(self):
        p=self.f.candidate_agent/'plugin.json';d=json.loads(p.read_text(encoding='utf-8'));d['hooks']={'new':'script'};p.write_text(json.dumps(d),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'execution_permission_change'):self.f.preflight()

    def test_dependency_tamper_stage_boundary_and_oversized_asset_block(self):
        a=self.delivery['assets']['report-kit-agent'];a['size']=64*1024*1024+1
        with self.assertRaisesRegex(ValueError,'asset_bounds'):self.stage()
        a['size']=self.downloads['report-kit-agent'].stat().st_size
        with self.assertRaisesRegex(ValueError,'stage_boundary'):
            updates.stage_candidate(self.source,self.delivery,self.observed,self.downloads,self.f.workspace/'stage',[self.f.workspace])

    def test_deferred_update_can_resume_without_changing_the_client(self):
        plan=self.f.preflight();host=self.host();host['active_runs']=['report']
        before=(self.f.workspace/'clients/first/AGENT.md').read_bytes()
        self.assertEqual(updates.installation_plan(plan,self.f.compatibility,self.f.candidate_skills,host,'2026-10-14T10:05:00Z')['status'],'DEFER_UNTIL_IDLE')
        host['active_runs']=[]
        self.assertEqual(updates.installation_plan(self.f.preflight(),self.f.compatibility,self.f.candidate_skills,host,'2026-10-14T10:05:00Z')['status'],'CHECK_CONSENT')
        self.assertEqual((self.f.workspace/'clients/first/AGENT.md').read_bytes(),before)

    def test_no_subprocess_or_network_execution_during_staging(self):
        with patch('subprocess.run',side_effect=AssertionError('No executed code')):
            self.assertEqual(self.stage()['status'],'STAGED_NOT_INSTALLED')

    def test_initial_install_failure_can_restore_absence_without_foreign_deletion(self):
        plan=updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)
        saved={'packages':self.f.old,'verified':True,'source_locator':'synthetic saved agent and confirmed absence', 'absent_packages':['report-kit-skills']}
        result=updates.activation_result(plan,saved,None,False)
        self.assertEqual(result['restore_absence'],['report-kit-skills'])
        self.assertEqual(result['client_data_writes'],[])

    def test_stale_host_observation_and_new_active_client_block(self):
        h=self.host();h['checked_at']='2026-10-12T00:00:00Z'
        with self.assertRaisesRegex(ValueError,'host_observation'):
            updates.installation_plan(self.f.preflight(),self.f.compatibility,self.f.candidate_skills,h,'2026-10-14T10:05:00Z')
        self.f.compatibility['clients']['second']['active_run']=True
        with self.assertRaisesRegex(ValueError,'active_run'):self.f.preflight()

    def test_host_double_rolls_back_pair_and_keeps_rules_settings_templates_history(self):
        plan=self.f.preflight();host_state=self.f.base/'fake-host-loaded.json'
        for name in ['templates/base.md','history/accepted.json','data/source.csv']:
            p=self.f.workspace/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'private fixture bytes')
        before={p.relative_to(self.f.workspace).as_posix():p.read_bytes() for p in self.f.workspace.rglob('*') if p.is_file()}
        host_state.write_text(json.dumps(self.f.new),encoding='utf-8')
        recovery=updates.activation_result(plan,{'packages':self.f.old,'verified':True,'source_locator':'synthetic host backup'},json.loads(host_state.read_text(encoding='utf-8')),False)
        # This is an isolated host double, not the real plugin installation mechanism.
        host_state.write_text(json.dumps(recovery['selected']),encoding='utf-8')
        self.assertEqual(json.loads(host_state.read_text(encoding='utf-8')),self.f.old)
        self.assertEqual(before,{p.relative_to(self.f.workspace).as_posix():p.read_bytes() for p in self.f.workspace.rglob('*') if p.is_file()})

    def test_archive_windows_names_and_file_parent_rejected_before_stage(self):
        for names in [['bad?.txt'],['CON.txt'],['safe','safe/child'],['é.txt','e\u0301.txt']]:
            out=io.BytesIO()
            with tarfile.open(fileobj=out,mode='w') as tar:
                for name in names:tar.addfile(tarfile.TarInfo(name))
            with self.assertRaises(ValueError):updates.archive_files(out.getvalue())

    def test_native_manifest_addition_is_a_separate_permission_decision(self):
        p=self.f.candidate_agent/'.codex-plugin/plugin.json';p.parent.mkdir();p.write_text('{"hooks": {"start":"new"}}',encoding='utf-8');self.inventory(self.f.candidate_agent)
        with self.assertRaisesRegex(ValueError,'execution_permission_change'):self.f.preflight()

    def test_cli_first_setup_delivery_and_stage_use_one_helper(self):
        for name,data in [('source',self.source),('delivery',self.delivery),('observed',self.observed),('downloads',{n:str(p) for n,p in self.downloads.items()}),('current',None)]:
            self.f.write(name+'.json',data)
        helper=Path(updates.__file__)
        def call(*args):
            r=subprocess.run([sys.executable,'-B',str(helper),*map(str,args)],capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr);return json.loads(r.stdout)
        w=self.f.workspace
        self.assertEqual(call('delivery',w/'source.json',w/'delivery.json',w/'observed.json')['status'],'READY_TO_DOWNLOAD')
        self.assertEqual(call('stage',w/'source.json',w/'delivery.json',w/'observed.json',w/'downloads.json',self.f.base/'stage','--protect-root',w)['status'],'STAGED_NOT_INSTALLED')

    def test_future_auto_update_choice_never_authorizes_initial_install(self):
        plan=updates.preflight(self.f.workspace,self.f.current_agent,None,*self.roots.values(),self.f.release,self.f.compat,'2026-10-14T10:05:00Z',bootstrap=True)
        policy=self.f.update_policy()
        self.assertEqual(updates.activation_decision(policy,self.source,plan,self.f.compatibility,'not_required')['route'],'ASK_FOR_INSTALL')


if __name__=='__main__':unittest.main()
