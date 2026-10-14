"""Synthetic committed package builds; no network, account, install or publication."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from check_package import identity
from prepare_release import prepare, verify_archive


class Releases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        def receipt_before_cleanup():
            for folder in [self.base/"artifact",self.base/"second"]:
                if folder.exists():
                    for path in sorted(p for p in folder.iterdir() if p.is_file()):
                        print(json.dumps({"temporary_path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                            "test":self.id(),"result":"Synthetic fixture inspected by assertions; cleanup follows"}))
        self.addCleanup(receipt_before_cleanup)
        self.skills = self.package("report-kit-skills")
        self.agent = self.package("report-kit-agent", self.skills)
        self.heads = {name: self.git(root, "rev-parse", "HEAD").stdout.strip()
            for name, root in [("report-kit-agent", self.agent), ("report-kit-skills", self.skills)]}
        self.output = self.base / "artifact"

    def git(self, root, *args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)

    def package(self, name, skills=None):
        root = self.base / name; root.mkdir()
        self.git(root, "init", "-b", "main")
        self.git(root, "config", "user.name", "Synthetic maintainer")
        self.git(root, "config", "user.email", "maintainer@example.invalid")
        files = {"VERSION": "0.1.0-dev.0\n", "plugin.json": json.dumps({"name":name,"version":"0.1.0-dev.0"}),
            ".agents/plugins/marketplace.json": json.dumps({"plugins":[{"name":name,"source":{"source":"local","path":"./"}}]}),
            "skills/livedune/SKILL.md": '---\nname: livedune\ndescription: "Synthetic fixture only"\n---\n',
            ".gitignore": ".token-optimizer/\n", "CHANGELOG.md": "# Synthetic changes\nTested fixture only\n"}
        if skills:
            files["dependencies.json"] = json.dumps({"report-kit-skills":{"version":"0.1.0-dev.0","package_sha256":identity(skills)}})
        else:
            files["capabilities.json"] = json.dumps({"schema_version":1,"package_version":"0.1.0-dev.0","capabilities":[{"name":"livedune","requires":[]}]})
        files["PUBLIC-FILES.json"] = json.dumps({"schema_version":1,"files":sorted([*files,"PUBLIC-FILES.json"])})
        for name, text in files.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        self.git(root, "add", "--", *files);self.git(root, "commit", "-m", "Synthetic committed payload")
        return root

    def build(self):
        return prepare(self.agent, self.skills, self.output, self.heads, "working")

    def test_exact_archives_and_draft_only(self):
        before = {name: identity(root) for name,root in [("report-kit-agent",self.agent),("report-kit-skills",self.skills)]}
        result = self.build()
        self.assertEqual(result["status"], "LOCAL_DRAFT_NOT_APPROVED")
        release=json.loads((self.output/"draft-release.json").read_text())
        self.assertFalse(release["published"])
        self.assertFalse(result["publication_authorized"])
        self.assertTrue(result["blockers"])
        for name,root in [("report-kit-agent",self.agent),("report-kit-skills",self.skills)]:
            tar=self.output/f"{name}-0.1.0-dev.0.tar"
            with tarfile.open(tar) as archive:
                paths={m.name for m in archive.getmembers() if m.isfile()}
                self.assertEqual(paths,set(json.loads((root/"PUBLIC-FILES.json").read_text())["files"]))
            self.assertEqual(identity(root),before[name])
            self.assertEqual(self.git(root,"status","--porcelain").stdout,"")
        self.assertEqual(set(result["artifacts"]),{p.name for p in self.output.iterdir() if p.name!="build-record.json"})

    def test_reproducible_committed_archive_bytes(self):
        first=self.build();self.output=self.base/"second";second=self.build()
        for name in ["report-kit-agent","report-kit-skills"]:
            filename=f"{name}-0.1.0-dev.0.tar"
            self.assertEqual(first["artifacts"][filename],second["artifacts"][filename])

    def test_dirty_wrong_commit_and_untracked_block_before_output(self):
        (self.agent/"VERSION").write_text("changed")
        with self.assertRaisesRegex(ValueError,"dirty_package"):self.build()
        self.assertFalse(self.output.exists())
        self.git(self.agent,"restore","--","VERSION")
        (self.agent/"untracked.txt").write_text("extra")
        with self.assertRaisesRegex(ValueError,"dirty_package"):self.build()
        (self.agent/"untracked.txt").unlink()
        self.heads["report-kit-agent"]="0"*40
        with self.assertRaisesRegex(ValueError,"commit_changed"):self.build()

    def test_existing_output_and_package_output_preserved(self):
        self.output.mkdir();marker=self.output/"keep.txt";marker.write_text("caller data")
        with self.assertRaisesRegex(ValueError,"output_exists"):self.build()
        self.assertEqual(marker.read_text(),"caller data")
        self.output=self.agent/"nested"
        with self.assertRaisesRegex(ValueError,"output_boundary"):self.build()
        self.assertFalse(self.output.exists())

    def test_ignored_caches_not_exported(self):
        cache=self.agent/".token-optimizer";cache.mkdir();(cache/"ignored.txt").write_text("private synthetic cache")
        self.build()
        with tarfile.open(self.output/"report-kit-agent-0.1.0-dev.0.tar") as archive:
            self.assertFalse(any(".token-optimizer" in m.name for m in archive.getmembers()))

    def test_git_export_attribute_cannot_hide_public_file(self):
        (self.agent/".gitattributes").write_text("CHANGELOG.md export-ignore\n")
        path=self.agent/"PUBLIC-FILES.json";data=json.loads(path.read_text())
        data["files"].append(".gitattributes");path.write_text(json.dumps(data))
        self.git(self.agent,"add","--",".gitattributes","PUBLIC-FILES.json")
        self.git(self.agent,"commit","-m","Synthetic export exclusion")
        self.heads["report-kit-agent"]=self.git(self.agent,"rev-parse","HEAD").stdout.strip()
        with self.assertRaisesRegex(ValueError,"archive_content"):self.build()
        self.assertFalse(self.output.exists())

    def test_archive_mutation_or_path_escape_rejected(self):
        expected={"safe.md":hashlib.sha256(b"safe").hexdigest()}
        for name,payload in [("safe.md",b"changed"),("../escape",b"safe")]:
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode="w") as archive:
                info=tarfile.TarInfo(name);info.size=len(payload);archive.addfile(info,io.BytesIO(payload))
            with self.assertRaises(ValueError):verify_archive(stream.getvalue(),expected)


if __name__=="__main__":unittest.main()
