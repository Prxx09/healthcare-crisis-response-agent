import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.config import Settings
from app.disease_codes import normalize_disease_code
from app.models import PredictiveAssessmentRequest
from app.playbook_documents import parse_playbook_document
from app.playbook_uploads import extract_actions, uploaded_response_plan
from app.pinecone_rag import select_response_plan_with_rag


def settings(**kwargs):
    return Settings(supabase_url='https://example.invalid',supabase_publishable_key='test',_env_file=None,**kwargs)


def action(text='NEW RULE'):
    return {'action_id':'0','condition_code':'cholera','condition_name':'Cholera','alert_level':'investigate',
            'action':text,'owner':'Laboratory lead','timeframe':'within 4 hours','requires_approval':True,'category':'investigation'}


def document():
    return {'id':'new-document','filename':'new.json','actions':[action()],'index_namespace':'new-only','status':'indexed','active':True}


class DynamicPlaybookTests(unittest.IsolatedAsyncioTestCase):
    def test_normalizes_explicit_names_and_existing_aliases(self):
        self.assertEqual(normalize_disease_code('Measles'),'measles')
        self.assertEqual(normalize_disease_code('COVID-19'),'covid_19')
        self.assertEqual(normalize_disease_code('Influenza-like Illness'),'ili')
        for invalid in ('', '123', {}, 'a'*81):
            with self.assertRaises(ValueError): normalize_disease_code(invalid)

    async def test_two_new_diseases_parse_directly(self):
        original=(Path(__file__).parent/'fixtures/dengue_sections.json').read_text()
        for code,name in [('measles','Measles'),('cholera','Cholera')]:
            raw=original.replace('dengue',code).replace('Dengue',name).encode()
            parsed=parse_playbook_document('new.json',raw)
            self.assertEqual(parsed['summary']['conditions'],[code])
            with patch('app.playbook_uploads.structure_section',new=AsyncMock(side_effect=AssertionError('Unexpected LLM'))):
                actions,method=await extract_actions('new.json',raw,raw.decode(),settings())
            self.assertEqual(len(actions),9);self.assertEqual(method,'structured')
            self.assertEqual({a['condition_name'] for a in actions},{name})

    async def test_new_disease_supported_in_existing_canonical_schema(self):
        payload={'version':'2','levels':{level:[{key:value for key,value in action().items() if key in {'action','owner','timeframe','requires_approval','category'}}] for level in ['monitor','investigate','escalate']},'condition_guidance':{'cholera':['Synthetic operational guidance.']}}
        raw=json.dumps(payload).encode()
        actions,_=await extract_actions('new.json',raw,raw.decode(),settings())
        self.assertEqual(len(actions),3)
        self.assertEqual({a['condition_code'] for a in actions},{'cholera'})

    async def test_llm_can_extract_a_new_explicit_disease(self):
        from app.playbook_uploads import structure_section
        quote='For Measles, the Laboratory lead must verify pending tests within 4 hours.'
        response=MagicMock();response.json.return_value={'choices':[{'message':{'content':json.dumps({'actions':[{
            'condition_code':'measles','condition_name':'Measles','alert_level':'investigate','evidence_quote':quote,
            'owner':'Laboratory lead','timeframe':'within 4 hours','category':'investigation'}]})}}]}
        client=AsyncMock();client.post.return_value=response
        context=MagicMock();context.__aenter__=AsyncMock(return_value=client);context.__aexit__=AsyncMock()
        with patch('app.playbook_uploads.httpx.AsyncClient',return_value=context):
            actions=await structure_section(quote,1,settings(ai_provider='groq',groq_api_key='test',groq_model='test'))
        self.assertEqual(actions[0]['condition_code'],'measles')
        self.assertEqual(actions[0]['condition_name'],'Measles')

    def test_predictive_request_accepts_registered_disease_codes(self):
        request=PredictiveAssessmentRequest(analysis_date='2026-10-21',hospital_code='north_hospital',condition_code='measles')
        self.assertEqual(request.condition_code,'measles')

    async def plan_with_repository(self, binding, docs=None, **kwargs):
        repo=MagicMock();repo.privileged_get=AsyncMock(side_effect=[[binding],docs or []])
        with patch('app.playbook_uploads.SupabaseRepository',return_value=repo):
            result=await uploaded_response_plan(settings(**kwargs),'cholera','investigate','query')
        return result,repo

    async def test_current_rules_work_without_semantic_ranking(self):
        result,repo=await self.plan_with_repository({'document_id':'new-document','enabled':True},[document()])
        self.assertEqual([a['action'] for a in result['actions']],['NEW RULE'])
        self.assertEqual(result['actions'][0]['source_document_id'],'new-document')
        self.assertEqual(repo.privileged_get.call_args.args[1]['id'],'eq.new-document')
        self.assertNotIn('OLD RULE',str(result))

    async def test_search_failure_uses_current_rules_only(self):
        with patch('app.playbook_uploads.query_document',side_effect=RuntimeError('search unavailable')):
            result,_=await self.plan_with_repository({'document_id':'new-document','enabled':True},[document()],pinecone_rag_enabled=True)
        self.assertEqual(result['actions'][0]['action'],'NEW RULE')
        self.assertEqual(result['retrieval']['status'],'current_rules_fallback')

    async def test_deactivated_override_never_restores_previous_rules(self):
        result,repo=await self.plan_with_repository({'document_id':'new-document','enabled':False})
        self.assertFalse(result['available']);self.assertEqual(result['actions'],[])
        self.assertEqual(repo.privileged_get.await_count,1)

    async def test_missing_alert_level_never_uses_bundled_rules(self):
        doc=document();doc['actions'][0]['alert_level']='monitor'
        result,_=await self.plan_with_repository({'document_id':'new-document','enabled':True},[doc])
        self.assertEqual(result['actions'],[]);self.assertIn('no actions',result['unavailable_reason'])

    async def test_unknown_registry_status_fails_instead_of_using_stale_rules(self):
        repo=MagicMock();repo.privileged_get=AsyncMock(side_effect=RuntimeError('database unavailable'))
        with patch('app.playbook_uploads.SupabaseRepository',return_value=repo):
            with self.assertRaisesRegex(RuntimeError,'Unable to verify current disease rules'):
                await uploaded_response_plan(settings(),'dengue','monitor','query')

    async def test_uploaded_new_disease_plan_bypasses_bundled_disease_restrictions(self):
        plan={'actions':[action()],'action_source':'uploaded','available':True}
        with patch('app.playbook_uploads.uploaded_response_plan',new=AsyncMock(return_value=plan)):
            result=await select_response_plan_with_rag(settings(),'cholera','investigate')
        self.assertEqual(result,plan)


if __name__=='__main__': unittest.main()
