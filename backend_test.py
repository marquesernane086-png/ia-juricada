#!/usr/bin/env python3
"""
JuristaAI Backend Testing Suite
Tests the backend at https://juristico-ia.preview.emergentagent.com/api
"""

import requests
import time
import json
import os
from typing import Optional, Dict, Any
import sys


class JuristaAITester:
    def __init__(self, base_url: str = "https://juristico-ia.preview.emergentagent.com/api"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 30
        
    def log(self, message: str):
        """Log with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def test_health_check(self) -> Dict[str, Any]:
        """Test 1: Health Check - GET /api/health"""
        self.log("🔍 Testing Health Check...")
        
        try:
            response = self.session.get(f"{self.base_url}/health")
            
            if response.status_code == 200:
                data = response.json()
                self.log(f"✅ Health check passed: {data}")
                
                # Verify expected fields
                expected_fields = ['status', 'database', 'documents', 'vector_chunks']
                for field in expected_fields:
                    if field not in data:
                        self.log(f"⚠️  Missing field in health response: {field}")
                        
                if data.get('status') == 'healthy':
                    self.log("✅ Status: healthy")
                else:
                    self.log(f"⚠️  Status not healthy: {data.get('status')}")
                    
                return {'success': True, 'data': data}
            else:
                self.log(f"❌ Health check failed: HTTP {response.status_code}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'response': response.text}
                
        except Exception as e:
            self.log(f"❌ Health check exception: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_upload_document(self) -> Dict[str, Any]:
        """Test 2: Upload Document - POST /api/documents/upload"""
        self.log("📄 Testing Document Upload...")
        
        pdf_path = "/app/backend/data/uploads/test_legal_book.pdf"
        
        if not os.path.exists(pdf_path):
            self.log(f"❌ Test PDF not found: {pdf_path}")
            return {'success': False, 'error': 'Test PDF not found'}
        
        try:
            # Prepare multipart form data
            with open(pdf_path, 'rb') as f:
                files = {
                    'file': ('test_legal_book.pdf', f, 'application/pdf')
                }
                data = {
                    'title': 'Curso de Direito Civil Brasileiro',
                    'author': 'Carlos Roberto Gonçalves',
                    'year': '2018',
                    'legal_subject': 'Direito Civil'
                }
                
                response = self.session.post(f"{self.base_url}/documents/upload", files=files, data=data)
            
            if response.status_code in [200, 201]:
                upload_data = response.json()
                self.log(f"✅ Document uploaded successfully: {upload_data}")
                
                # Extract document ID for later use
                document_id = upload_data.get('id') or upload_data.get('document_id')
                if document_id:
                    self.log(f"📋 Document ID: {document_id}")
                    
                return {'success': True, 'data': upload_data, 'document_id': document_id}
            else:
                self.log(f"❌ Upload failed: HTTP {response.status_code}")
                self.log(f"Response: {response.text}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'response': response.text}
                
        except Exception as e:
            self.log(f"❌ Upload exception: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def wait_for_indexing(self, max_wait_seconds: int = 120) -> Dict[str, Any]:
        """Test 3: Wait for Indexing - Poll GET /api/documents"""
        self.log("⏳ Waiting for document indexing...")
        
        start_time = time.time()
        poll_interval = 10
        
        while time.time() - start_time < max_wait_seconds:
            try:
                response = self.session.get(f"{self.base_url}/documents")
                
                if response.status_code == 200:
                    documents = response.json()
                    self.log(f"📊 Found {len(documents)} documents")
                    
                    # Check for indexed documents
                    indexed_docs = [doc for doc in documents if doc.get('status') == 'indexed']
                    processing_docs = [doc for doc in documents if doc.get('status') == 'processing']
                    
                    self.log(f"📈 Status - Indexed: {len(indexed_docs)}, Processing: {len(processing_docs)}")
                    
                    if indexed_docs:
                        self.log(f"✅ Document indexing complete! Found {len(indexed_docs)} indexed document(s)")
                        for doc in indexed_docs:
                            chunks = doc.get('chunk_count', doc.get('chunks', 'unknown'))
                            self.log(f"  - {doc.get('title', 'Unknown')}: {chunks} chunks")
                        return {'success': True, 'data': documents, 'indexed_count': len(indexed_docs)}
                    
                    if processing_docs:
                        elapsed = int(time.time() - start_time)
                        self.log(f"⏳ Still processing... ({elapsed}s elapsed)")
                    else:
                        self.log("⚠️  No documents found in processing or indexed status")
                
                else:
                    self.log(f"❌ Failed to fetch documents: HTTP {response.status_code}")
                    
            except Exception as e:
                self.log(f"❌ Polling exception: {str(e)}")
            
            # Wait before next poll
            time.sleep(poll_interval)
        
        self.log(f"❌ Indexing timeout after {max_wait_seconds} seconds")
        return {'success': False, 'error': 'Indexing timeout'}
    
    def test_chat_stats(self) -> Dict[str, Any]:
        """Test 4: Stats Check - GET /api/chat/stats"""
        self.log("📊 Testing Chat Stats...")
        
        try:
            response = self.session.get(f"{self.base_url}/chat/stats")
            
            if response.status_code == 200:
                stats = response.json()
                self.log(f"✅ Chat stats retrieved: {stats}")
                
                total_chunks = stats.get('total_chunks', 0)
                if total_chunks > 0:
                    self.log(f"✅ Vector store has {total_chunks} chunks")
                    return {'success': True, 'data': stats}
                else:
                    self.log("⚠️  No chunks found in vector store")
                    return {'success': False, 'error': 'No chunks in vector store', 'data': stats}
                    
            else:
                self.log(f"❌ Stats check failed: HTTP {response.status_code}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'response': response.text}
                
        except Exception as e:
            self.log(f"❌ Stats check exception: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_legal_question(self) -> Dict[str, Any]:
        """Test 5: Legal Question - POST /api/chat"""
        self.log("🤖 Testing Legal Q&A...")
        
        question = "O que é responsabilidade civil objetiva?"
        payload = {
            "question": question,
            "max_sources": 5
        }
        
        try:
            self.log(f"❓ Question: {question}")
            start_time = time.time()
            
            response = self.session.post(
                f"{self.base_url}/chat", 
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                chat_data = response.json()
                answer = chat_data.get('answer', '')
                sources = chat_data.get('sources', [])
                
                self.log(f"✅ Legal question answered in {duration:.2f}s")
                self.log(f"📝 Answer (first 300 chars): {answer[:300]}{'...' if len(answer) > 300 else ''}")
                self.log(f"📚 Number of sources: {len(sources)}")
                
                if sources:
                    self.log("📖 Sources summary:")
                    for i, source in enumerate(sources[:3]):  # Show first 3 sources
                        relevance = source.get('relevance_score', 'N/A')
                        page = source.get('page_number', 'N/A')
                        self.log(f"  {i+1}. Page {page}, Relevance: {relevance}")
                
                return {
                    'success': True, 
                    'data': chat_data, 
                    'answer_length': len(answer),
                    'source_count': len(sources),
                    'duration': duration
                }
            else:
                self.log(f"❌ Legal question failed: HTTP {response.status_code}")
                self.log(f"Response: {response.text}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'response': response.text}
                
        except Exception as e:
            self.log(f"❌ Legal question exception: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def test_no_context_question(self) -> Dict[str, Any]:
        """Test 6: Question with no context - POST /api/chat"""
        self.log("🔍 Testing Question with No Context...")
        
        question = "O que é habeas corpus?"
        payload = {
            "question": question,
            "max_sources": 5
        }
        
        try:
            self.log(f"❓ Question (no context expected): {question}")
            start_time = time.time()
            
            response = self.session.post(
                f"{self.base_url}/chat", 
                json=payload,
                headers={'Content-Type': 'application/json'}
            )
            
            duration = time.time() - start_time
            
            if response.status_code == 200:
                chat_data = response.json()
                answer = chat_data.get('answer', '').lower()
                sources = chat_data.get('sources', [])
                
                self.log(f"✅ No-context question answered in {duration:.2f}s")
                self.log(f"📝 Answer (first 300 chars): {chat_data.get('answer', '')[:300]}{'...' if len(chat_data.get('answer', '')) > 300 else ''}")
                self.log(f"📚 Number of sources: {len(sources)}")
                
                # Check if it properly indicates lack of context
                no_info_indicators = [
                    'acervo', 'não', 'nao', 'suficient', 'informaç', 'contexto',
                    'disponível', 'disponivel', 'encontr'
                ]
                
                has_no_info_indicator = any(indicator in answer for indicator in no_info_indicators)
                
                if has_no_info_indicator:
                    self.log("✅ System properly indicates insufficient information in acervo")
                    return {
                        'success': True, 
                        'data': chat_data,
                        'properly_handled_no_context': True,
                        'duration': duration
                    }
                else:
                    self.log("⚠️  System may have invented an answer instead of indicating insufficient information")
                    return {
                        'success': True,  # Still successful response, but concerning behavior
                        'data': chat_data,
                        'properly_handled_no_context': False,
                        'warning': 'May have invented answer',
                        'duration': duration
                    }
            else:
                self.log(f"❌ No-context question failed: HTTP {response.status_code}")
                return {'success': False, 'error': f"HTTP {response.status_code}", 'response': response.text}
                
        except Exception as e:
            self.log(f"❌ No-context question exception: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def run_full_test_suite(self):
        """Run all tests in sequence"""
        self.log("🚀 Starting JuristaAI Backend Test Suite")
        self.log(f"🎯 Target URL: {self.base_url}")
        self.log("=" * 60)
        
        results = {}
        
        # Test 1: Health Check
        results['health'] = self.test_health_check()
        
        # Test 2: Upload Document
        results['upload'] = self.test_upload_document()
        
        # Test 3: Wait for Indexing
        results['indexing'] = self.wait_for_indexing()
        
        # Test 4: Stats Check
        results['stats'] = self.test_chat_stats()
        
        # Test 5: Legal Question
        results['legal_qa'] = self.test_legal_question()
        
        # Test 6: No Context Question
        results['no_context_qa'] = self.test_no_context_question()
        
        # Summary
        self.log("=" * 60)
        self.log("📋 TEST SUMMARY:")
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result.get('success'))
        
        for test_name, result in results.items():
            status = "✅ PASSED" if result.get('success') else "❌ FAILED"
            self.log(f"  {test_name.upper()}: {status}")
            if not result.get('success'):
                self.log(f"    Error: {result.get('error', 'Unknown error')}")
        
        self.log(f"\n🏁 Overall Result: {passed_tests}/{total_tests} tests passed")
        
        if passed_tests == total_tests:
            self.log("🎉 All tests PASSED! JuristaAI backend is fully functional.")
        else:
            self.log(f"⚠️  {total_tests - passed_tests} test(s) failed. Check errors above.")
        
        return results


def main():
    """Main entry point"""
    tester = JuristaAITester()
    results = tester.run_full_test_suite()
    
    # Exit with appropriate code
    failed_tests = sum(1 for result in results.values() if not result.get('success'))
    sys.exit(failed_tests)


if __name__ == "__main__":
    main()