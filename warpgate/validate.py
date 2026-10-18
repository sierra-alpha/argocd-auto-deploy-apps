#!/usr/bin/env python3
"""Offline regression checks for the disabled PoC's security boundaries."""
import copy
import os
from pathlib import Path
import subprocess
import unittest

import yaml

ROOT = Path(__file__).resolve().parent


def load(text):
    return [item for item in yaml.safe_load_all(text) if item]


def one(docs, kind):
    matches = [d for d in docs if d['kind'] == kind]
    assert len(matches) == 1, kind
    return matches[0]


def check(docs):
    assert {d['kind'] for d in docs} == {
        'Namespace', 'ServiceAccount', 'ConfigMap', 'Deployment', 'Service', 'NetworkPolicy'
    }, 'Unexpected resources (no Secrets, hooks, routes, or PVC lifecycle)'
    dep = one(docs, 'Deployment')['spec']
    assert dep['replicas'] == 0, 'PoC must stay scaled to zero'
    assert dep['strategy'] == {'type': 'Recreate'}
    pod = dep['template']['spec']
    assert pod['automountServiceAccountToken'] is False
    assert one(docs, 'ServiceAccount')['automountServiceAccountToken'] is False
    assert pod['securityContext']['runAsNonRoot'] is True
    assert pod['securityContext']['runAsUser'] == 1000
    assert pod['securityContext']['seccompProfile']['type'] == 'RuntimeDefault'
    assert not pod.get('hostNetwork') and not pod.get('hostPID') and not pod.get('hostIPC')
    for c in pod['containers'] + pod['initContainers']:
        assert c['image'] == 'ghcr.io/warp-tech/warpgate:0.29.2'
        sc = c['securityContext']
        assert sc['allowPrivilegeEscalation'] is False
        assert sc['readOnlyRootFilesystem'] is True
        assert sc['capabilities']['drop'] == ['ALL']
        assert not sc.get('privileged')
        assert set(c['resources']['requests']) == {'cpu', 'memory'}
        assert set(c['resources']['limits']) == {'cpu', 'memory'}
        assert all('value' not in e for e in c.get('env', []))
    main = pod['containers'][0]
    key = next(e for e in main['env'] if e['name'] == 'WARPGATE_ENCRYPTION_KEY')
    assert key['valueFrom']['secretKeyRef'] == {'name': 'warpgate-encryption', 'key': 'encryptionKey'}
    assert not pod['initContainers'][0].get('env'), 'Bootstrap credentials must not enter normal pod'
    for probe in ('startupProbe', 'readinessProbe', 'livenessProbe'):
        assert main[probe]['httpGet'] == {'scheme': 'HTTPS', 'path': '/@warpgate/api/info', 'port': 'http'}
    assert {p['containerPort'] for p in main['ports']} == {2222, 8888}
    volumes = {v['name']: v for v in pod['volumes']}
    assert volumes['data']['persistentVolumeClaim']['claimName'] == 'warpgate-data'
    assert volumes['tls-cert']['secret']['secretName'] == 'warpgate-tls'
    assert all('hostPath' not in v for v in pod['volumes'])
    svc = one(docs, 'Service')
    assert not svc['metadata'].get('annotations')
    assert svc['spec']['type'] == 'ClusterIP'
    assert not svc['spec'].get('externalIPs')
    assert {p['port'] for p in svc['spec']['ports']} == {2222, 8888}
    assert all('nodePort' not in p for p in svc['spec']['ports'])
    policy = one(docs, 'NetworkPolicy')['spec']
    assert policy == {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'], 'ingress': [], 'egress': []}
    cfg = yaml.safe_load(one(docs, 'ConfigMap')['data']['warpgate.yaml'])
    assert cfg['database_url'] == 'sqlite:/data/db'
    assert cfg['http']['listen'] == '0.0.0.0:8888'
    assert cfg['ssh'] == {'enable': True, 'listen': '0.0.0.0:2222'}
    assert all(cfg[p]['enable'] is False for p in ('mysql', 'postgres', 'kubernetes', 'rdp', 'vnc'))
    assert cfg['recordings'] == {'enable': True, 'path': '/data/recordings'}
    assert one(docs, 'Namespace')['metadata']['labels']['pod-security.kubernetes.io/enforce'] == 'restricted'


class Safety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rendered = subprocess.check_output(['sh', str(ROOT / 'render.sh')], text=True)
        again = subprocess.check_output(['sh', str(ROOT / 'render.sh')], text=True)
        assert rendered == again, 'Nondeterministic chart output'
        assert rendered == (ROOT / 'manifests/upstream.yaml').read_text(), 'Regenerate upstream.yaml'
        cls.docs = load(subprocess.check_output(
            [os.environ.get('KUSTOMIZE', 'kustomize'), 'build', str(ROOT / 'manifests')], text=True))

    def test_safe_render(self):
        check(self.docs)

    def test_opt_in_application(self):
        app = yaml.safe_load((ROOT / 'application.yaml.example').read_text())
        assert app['spec']['syncPolicy'] == {}
        assert 'finalizers' not in app['metadata']
        assert app['spec']['source']['targetRevision'] == 'REPLACE_WITH_REVIEWED_COMMIT_SHA'
        assert app['spec']['source']['path'] == 'warpgate/manifests'
        for path in (ROOT.parent / 'app-of-apps').rglob('*'):
            if path.is_file():
                assert 'warpgate' not in path.read_text().lower(), path

    def test_reject_accidental_rollout(self):
        docs = copy.deepcopy(self.docs)
        one(docs, 'Deployment')['spec']['replicas'] = 1
        with self.assertRaises(AssertionError):
            check(docs)

    def test_reject_public_service(self):
        docs = copy.deepcopy(self.docs)
        one(docs, 'Service')['spec']['type'] = 'LoadBalancer'
        with self.assertRaises(AssertionError):
            check(docs)

    def test_reject_missing_encryption_secret(self):
        docs = copy.deepcopy(self.docs)
        env = one(docs, 'Deployment')['spec']['template']['spec']['containers'][0]['env']
        next(e for e in env if e['name'] == 'WARPGATE_ENCRYPTION_KEY')['valueFrom']['secretKeyRef']['optional'] = True
        with self.assertRaises(AssertionError):
            check(docs)

    def test_reject_open_network(self):
        docs = copy.deepcopy(self.docs)
        one(docs, 'NetworkPolicy')['spec']['ingress'] = [{}]
        with self.assertRaises(AssertionError):
            check(docs)

    def test_reject_extra_listener(self):
        docs = copy.deepcopy(self.docs)
        cm = one(docs, 'ConfigMap')['data']
        cfg = yaml.safe_load(cm['warpgate.yaml'])
        cfg['rdp']['enable'] = True
        cm['warpgate.yaml'] = yaml.safe_dump(cfg)
        with self.assertRaises(AssertionError):
            check(docs)


if __name__ == '__main__':
    unittest.main(verbosity=2)
