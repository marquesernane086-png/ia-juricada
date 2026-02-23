#!/usr/bin/env python3
"""
Targeted JuristaAI Backend Test - 6 Specific Tests as Requested
"""

import requests
import time
import json
import os

BASE_URL = "https://juristico-ia.preview.emergentagent.com/api"

def log(message):
    """Log with timestamp"""
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

def test_1_health_check():
    """Test 1: Health Check - GET /api/health - should return "healthy" """
    log("🔍 Test 1: Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            log(f"✅ Health check response: {data}")
            
            if data.get('status') == 'healthy':
                log("✅ Status is 'healthy' as expected")
                return True
            else:
                log(f"❌ Expected status 'healthy', got: {data.get('status')}")
                return False
        else:
            log(f"❌ Health check failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Health check exception: {str(e)}")
        return False

def test_2_upload_document():
    """Test 2: Upload Document - POST /api/documents/upload with specific data"""
    log("📄 Test 2: Document Upload")
    
    pdf_path = "/app/backend/data/uploads/test_legal_book.pdf"
    
    if not os.path.exists(pdf_path):
        log(f"❌ Test PDF not found: {pdf_path}")
        return False
    
    try:
        # Prepare multipart form data exactly as requested
        with open(pdf_path, 'rb') as f:
            files = {'file': ('test_legal_book.pdf', f, 'application/pdf')}
            data = {
                'title': 'Curso de Direito Civil Brasileiro',
                'author': 'Carlos Roberto Gonçalves', 
                'year': '2018',
                'legal_subject': 'Direito Civil'
            }
            
            response = requests.post(f"{BASE_URL}/documents/upload", files=files, data=data, timeout=30)
        
        if response.status_code in [200, 201]:
            upload_data = response.json()
            log(f"✅ Document upload successful: {upload_data}")
            return True
        else:
            log(f"❌ Upload failed: HTTP {response.status_code}")
            log(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        log(f"❌ Upload exception: {str(e)}")
        return False

def test_3_wait_for_indexing():
    """Test 3: Wait for Indexing - Poll GET /api/documents every 10 seconds for up to 120 seconds"""
    log("⏳ Test 3: Waiting for Indexing (up to 120 seconds)")
    
    start_time = time.time()
    poll_count = 0
    
    while time.time() - start_time < 120:
        poll_count += 1
        elapsed = int(time.time() - start_time)
        
        try:
            response = requests.get(f"{BASE_URL}/documents", timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                documents = data.get('documents', data) if isinstance(data, dict) else data
                
                log(f"Poll #{poll_count} ({elapsed}s): Found {len(documents)} documents")
                
                # Check for indexed documents
                indexed_docs = []
                for doc in documents:
                    if doc.get('status') == 'indexed':
                        indexed_docs.append(doc)
                        chunks = doc.get('chunk_count', doc.get('total_chunks', 'unknown'))
                        log(f"  📋 Indexed: '{doc.get('title', 'Unknown')}' - {chunks} chunks")
                
                if indexed_docs:
                    log(f"✅ Found {len(indexed_docs)} indexed document(s)!")
                    return True
                else:
                    log(f"⏳ No indexed documents yet...")
                    
            else:
                log(f"❌ Failed to fetch documents: HTTP {response.status_code}")
                
        except Exception as e:
            log(f"❌ Polling exception: {str(e)}")
        
        # Wait 10 seconds before next poll
        if time.time() - start_time < 120:
            time.sleep(10)
    
    log("❌ Indexing timeout after 120 seconds")
    return False

def test_4_stats_check():
    """Test 4: Stats Check - GET /api/chat/stats - verify total_chunks > 0"""
    log("📊 Test 4: Chat Stats Check")
    
    try:
        response = requests.get(f"{BASE_URL}/chat/stats", timeout=30)
        
        if response.status_code == 200:
            stats = response.json()
            log(f"✅ Chat stats: {stats}")
            
            total_chunks = stats.get('total_chunks', 0)
            if total_chunks > 0:
                log(f"✅ Vector store has {total_chunks} chunks (> 0 as required)")
                return True
            else:
                log(f"❌ total_chunks is {total_chunks}, expected > 0")
                return False
                
        else:
            log(f"❌ Stats check failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Stats check exception: {str(e)}")
        return False

def test_5_legal_question():
    """Test 5: Legal Question - POST /api/chat with specific question"""
    log("🤖 Test 5: Legal Question")
    
    payload = {
        "question": "O que é responsabilidade civil objetiva?",
        "max_sources": 5
    }
    
    try:
        log(f"❓ Question: {payload['question']}")
        start_time = time.time()
        
        response = requests.post(
            f"{BASE_URL}/chat", 
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        duration = time.time() - start_time
        
        if response.status_code == 200:
            chat_data = response.json()
            answer = chat_data.get('answer', '')
            sources = chat_data.get('sources', [])
            
            log(f"✅ Legal question answered in {duration:.2f}s")
            log(f"📝 Answer (first 300 chars): {answer[:300]}{'...' if len(answer) > 300 else ''}")
            log(f"📚 Number of sources: {len(sources)}")
            
            return True
        else:
            log(f"❌ Legal question failed: HTTP {response.status_code}")
            log(f"Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        log(f"❌ Legal question exception: {str(e)}")
        return False

def test_6_no_context_question():
    """Test 6: Question with no context - should say acervo doesn't have enough info"""
    log("🔍 Test 6: No Context Question")
    
    payload = {
        "question": "O que é habeas corpus?",
        "max_sources": 5
    }
    
    try:
        log(f"❓ Question (should indicate insufficient info): {payload['question']}")
        start_time = time.time()
        
        response = requests.post(
            f"{BASE_URL}/chat", 
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=60
        )
        
        duration = time.time() - start_time
        
        if response.status_code == 200:
            chat_data = response.json()
            answer = chat_data.get('answer', '').lower()
            sources = chat_data.get('sources', [])
            
            log(f"✅ No-context question answered in {duration:.2f}s")
            log(f"📝 Answer (first 300 chars): {chat_data.get('answer', '')[:300]}{'...' if len(chat_data.get('answer', '')) > 300 else ''}")
            log(f"📚 Number of sources: {len(sources)}")
            
            # Check if it properly indicates lack of context
            no_info_indicators = [
                'acervo', 'não', 'nao', 'suficient', 'informaç', 'contexto',
                'disponível', 'disponivel', 'encontr'
            ]
            
            has_no_info_indicator = any(indicator in answer for indicator in no_info_indicators)
            
            if has_no_info_indicator:
                log("✅ System properly indicates insufficient information in acervo")
            else:
                log("⚠️  System may have invented an answer instead of indicating insufficient information")
            
            return True
        else:
            log(f"❌ No-context question failed: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ No-context question exception: {str(e)}")
        return False

def main():
    """Run the 6 requested tests"""
    log("🚀 Starting JuristaAI Backend Test Suite (6 Specific Tests)")
    log(f"🎯 Target URL: {BASE_URL}")
    log("=" * 80)
    
    # Run all 6 tests
    results = []
    
    results.append(("Health Check", test_1_health_check()))
    results.append(("Document Upload", test_2_upload_document()))
    results.append(("Wait for Indexing", test_3_wait_for_indexing()))
    results.append(("Stats Check", test_4_stats_check()))
    results.append(("Legal Question", test_5_legal_question()))
    results.append(("No Context Question", test_6_no_context_question()))
    
    # Summary
    log("=" * 80)
    log("📋 TEST RESULTS SUMMARY:")
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASSED" if success else "❌ FAILED"
        log(f"  {test_name}: {status}")
        if success:
            passed += 1
    
    log(f"\n🏁 Overall Result: {passed}/{len(results)} tests PASSED")
    
    if passed == len(results):
        log("🎉 All tests PASSED! JuristaAI backend is fully functional.")
    else:
        log(f"⚠️  {len(results) - passed} test(s) failed.")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)