#!/usr/bin/env python3
import copy
import os
from pathlib import Path
import subprocess
import unittest
import yaml
ROOT = Path(__file__).resolve().parent

def index(docs):
    return {(d['kind'],d['metadata']['name']):d for d in docs if d}

def check(d):
    dep=d['Deployment','warpgate']; pod=dep['spec']['template']['spec']
    assert dep['spec']['replicas']==1 and dep['spec']['strategy']=={'type':'Recreate'}
    assert pod['automountServiceAccountToken'] is False
    assert pod['securityContext']['runAsNonRoot'] is True
    assert pod['securityContext']['seccompProfile']=={'type':'RuntimeDefault'}
    for c in pod['containers']+pod['initContainers']:
        assert c['image']=='ghcr.io/warp-tech/warpgate:0.29.2'
        assert c['securityContext']['allowPrivilegeEscalation'] is False
        assert c['securityContext']['readOnlyRootFilesystem'] is True
        assert c['securityContext']['capabilities']=={'drop':['ALL']}
        assert set(c['resources']['limits'])=={'cpu','memory'}
        for e in c.get('env',[]):
            assert 'value' not in e
            assert not e['valueFrom'].get('secretKeyRef',{}).get('optional',False)
    main=pod['containers'][0]; init=pod['initContainers'][0]
    assert {e['name'] for e in main['env']}=={'POD_IP','WARPGATE_ENCRYPTION_KEY'}
    assert {e['name'] for e in init['env']}=={'WARPGATE_NEW_USER_PASSWORD','WARPGATE_ENCRYPTION_KEY','WARPGATE_ADMIN_USERNAME'}
    assert {e['valueFrom']['secretKeyRef']['key'] for e in init['env']}=={'username','password','encryption-key'}
    assert all(e['valueFrom']['secretKeyRef']['name']=='warpgate' for e in init['env'])
    assert 'create-user --role warpgate:admin "$WARPGATE_ADMIN_USERNAME"' in init['command'][-1]
    assert '--password' not in init['command'][-1]
    assert any(m['mountPath']=='/tls-cert' and m['readOnly'] for m in main['volumeMounts'])
    assert 'sha256sum /tls-cert/tls.crt /tls-cert/tls.key' in main['command'][-1]
    for p in ('readinessProbe','livenessProbe','startupProbe'):
        assert main[p]['httpGet']['scheme']=='HTTPS'
    svc=d['Service','warpgate']
    assert svc['spec']['type']=='ClusterIP'
    assert svc['metadata']['annotations']=={'tailscale.com/expose':'true','tailscale.com/hostname':'warpgate'}
    assert {p['port'] for p in svc['spec']['ports']}=={443,2222}
    assert not any(k in {'Secret','Ingress','HTTPRoute','Job','Role','ClusterRole'} for k,n in d)
    for name in ('warpgate',):
        assert d['OnePasswordItem',name]['spec']['itemPath']=='vaults/K8s Service Account/items/'+name
    cert=d['Certificate','warpgate']['spec']
    assert cert['secretName']=='warpgate-tls'
    assert cert['issuerRef']=={'name':'letsencrypt-production','kind':'ClusterIssuer'}
    assert cert['dnsNames']==['warpgate.app.sierraalpha.co.nz']
    deny=d['NetworkPolicy','warpgate-default-deny']['spec']
    assert deny=={'podSelector':{},'policyTypes':['Ingress','Egress'],'ingress':[],'egress':[]}
    allow=d['NetworkPolicy','warpgate-tailnet-ingress']['spec']
    assert allow['policyTypes']==['Ingress']
    rule=allow['ingress'][0]
    assert len(rule['from'])==1
    peer=rule['from'][0]
    assert peer['namespaceSelector']['matchLabels']=={'kubernetes.io/metadata.name':'tailscale'}
    assert peer['podSelector']['matchLabels']=={'tailscale.com/managed':'true','tailscale.com/parent-resource-type':'svc','tailscale.com/parent-resource':'warpgate','tailscale.com/parent-resource-ns':'warpgate'}
    assert {p['port'] for p in rule['ports']}=={2222,8888}
    # Only LAN clients through Traefik may reach the new web route.
    # Tailnet access remains through its existing, separate Tailscale proxy.
    lan=d['NetworkPolicy','warpgate-traefik-lan-ingress']['spec']
    assert lan['policyTypes']==['Ingress']
    lan_rule=lan['ingress'][0]
    assert len(lan_rule['from'])==1
    assert lan_rule['from'][0]=={
        'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},
        'podSelector':{'matchLabels':{'app.kubernetes.io/name':'traefik'}}
    }
    assert lan_rule['ports']==[{'protocol':'TCP','port':8888}]
    assert lan['podSelector']==allow['podSelector']
    middleware=d['Middleware','warpgate-lan-only']
    assert middleware['apiVersion']=='traefik.io/v1alpha1'
    assert middleware['spec']=={'ipAllowList':{'sourceRange':['192.168.1.0/24']}}
    transport=d['ServersTransport','warpgate-verified-upstream']
    assert transport['spec']=={'serverName':'warpgate.app.sierraalpha.co.nz'}
    route=d['IngressRoute','warpgate-lan']
    assert route['apiVersion']=='traefik.io/v1alpha1'
    assert route['spec']=={
        'entryPoints':['websecure'],
        'routes':[{
            'kind':'Rule',
            'match':'Host(`warpgate.app.sierraalpha.co.nz`)',
            'middlewares':[{'name':'warpgate-lan-only'}],
            'services':[{'name':'warpgate','port':443,'scheme':'https',
                         'serversTransport':'warpgate-verified-upstream'}]
        }],
        'tls':{'secretName':'warpgate-tls'}
    }
    cfg=yaml.safe_load(d['ConfigMap','warpgate-config-overrides']['data']['warpgate.yaml'])
    assert cfg['http']['certificate']=='/tls-cert/tls.crt'
    assert cfg['http']['key']=='/tls-cert/tls.key'
    assert all(cfg[p]['enable'] is False for p in ('mysql','postgres','kubernetes','rdp','vnc'))
    assert d['PersistentVolumeClaim','warpgate-data']['metadata']['annotations']['argocd.argoproj.io/sync-options']=='Prune=false,Delete=false'

class Activation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output=subprocess.check_output(['sh',str(ROOT/'render.sh')],text=True)
        assert output==subprocess.check_output(['sh',str(ROOT/'render.sh')],text=True)
        assert output==(ROOT/'manifests/upstream.yaml').read_text()
        cls.docs=index(yaml.safe_load_all(subprocess.check_output([os.environ.get('KUSTOMIZE','kustomize'),'build',str(ROOT/'manifests')],text=True)))
    def test_render(self): check(self.docs)
    def test_application(self):
        a=yaml.safe_load((ROOT.parent/'app-of-apps/warpgate.yaml').read_text())
        assert a['spec']['source']['path']=='warpgate/manifests'
        assert a['spec']['syncPolicy']['automated']=={'prune':False,'selfHeal':True}
        assert not a['metadata'].get('finalizers')
    def test_reject_public_service(self):
        d=copy.deepcopy(self.docs);d['Service','warpgate']['spec']['type']='LoadBalancer'
        with self.assertRaises(AssertionError): check(d)
    def test_reject_optional_key(self):
        d=copy.deepcopy(self.docs)
        env=d['Deployment','warpgate']['spec']['template']['spec']['containers'][0]['env']
        next(e for e in env if e['name']=='WARPGATE_ENCRYPTION_KEY')['valueFrom']['secretKeyRef']['optional']=True
        with self.assertRaises(AssertionError): check(d)
    def test_reject_blanket_ingress(self):
        d=copy.deepcopy(self.docs);d['NetworkPolicy','warpgate-tailnet-ingress']['spec']['ingress'][0]['from'][0]['podSelector']={}
        with self.assertRaises((AssertionError,KeyError)): check(d)
    def test_reject_public_lan_allowlist(self):
        d=copy.deepcopy(self.docs)
        d['Middleware','warpgate-lan-only']['spec']['ipAllowList']['sourceRange']=['0.0.0.0/0']
        with self.assertRaises(AssertionError): check(d)
    def test_reject_lan_plaintext_backend(self):
        d=copy.deepcopy(self.docs)
        d['IngressRoute','warpgate-lan']['spec']['routes'][0]['services'][0]['scheme']='http'
        with self.assertRaises(AssertionError): check(d)
    def test_reject_traefik_access_to_ssh(self):
        d=copy.deepcopy(self.docs)
        d['NetworkPolicy','warpgate-traefik-lan-ingress']['spec']['ingress'][0]['ports'].append({'protocol':'TCP','port':2222})
        with self.assertRaises(AssertionError): check(d)
    def test_reject_egress_open(self):
        d=copy.deepcopy(self.docs);d['NetworkPolicy','warpgate-default-deny']['spec']['egress']=[{}]
        with self.assertRaises(AssertionError): check(d)
if __name__=='__main__': unittest.main(verbosity=2)
