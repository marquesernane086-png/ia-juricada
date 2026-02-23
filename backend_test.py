#!/usr/bin/env python3
"""
JuristaAI Backend API Tests
Tests the main functionality of the JuristaAI legal document processing system.
"""

import requests
import json
import time
import os
from pathlib import Path
import sys

# Test configuration
BASE_URL = "https://juristico-ia.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"
TEST_PDF_PATH = "/app/backend/data/uploads/test_legal_book.pdf"

# Test data
TEST_DOCUMENT_DATA = {
    "title": "Curso de Direito Civil Brasileiro",
    "author": "Carlos Roberto Gonçalves",
    "year": 2018,
    "legal_subject": "Direito Civil",
    "legal_institute": "Responsabilidade Civil"
}

TEST_QUESTIONS = [
    "O que é responsabilidade civil objetiva?",
    "Quais são os pressupostos da responsabilidade civil?"
]


def print_test_header(test_name):
    """Print formatted test header"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")


def print_result(success, message):
    """Print formatted test result"""
    status = "✅ PASS" if success else "❌ FAIL"
    print(f"{status}: {message}")


def test_health_check():
    """Test 1: Health Check"""
    print_test_header("Health Check")
    
    try:
        response = requests.get(f"{API_BASE}/health", timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {json.dumps(data, indent=2)}")
            
            if data.get("status") == "healthy":
                print_result(True, "Health check returned 'healthy' status")
                return True
            else:
                print_result(False, f"Health check returned unexpected status: {data.get('status')}")
                return False
        else:
            print_result(False, f"Health check failed with status {response.status_code}")
            return False
            
    except Exception as e:
        print_result(False, f"Health check failed with exception: {e}")
        return False


def test_document_upload():
    """Test 2: Upload Document"""
    print_test_header("Document Upload")
    
    try:
        # Check if test file exists
        if not os.path.exists(TEST_PDF_PATH):
            print_result(False, f"Test PDF file not found at: {TEST_PDF_PATH}")
            return None
            
        # Prepare file upload
        with open(TEST_PDF_PATH, 'rb') as f:
            files = {
                'file': (os.path.basename(TEST_PDF_PATH), f, 'application/pdf')
            }
            
            data = TEST_DOCUMENT_DATA
            
            print(f"Uploading file: {TEST_PDF_PATH}")
            print(f"Upload data: {json.dumps(data, indent=2)}")
            
            response = requests.post(f"{API_BASE}/documents/upload", files=files, data=data, timeout=30)
            print(f"Response status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"Upload response: {json.dumps(result, indent=2)}")
                
                if result.get("status") in ["processing", "duplicate"]:
                    document_id = result.get("id")
                    print_result(True, f"Document uploaded successfully with ID: {document_id}")
                    return document_id
                else:
                    print_result(False, f"Unexpected upload status: {result.get('status')}")
                    return None
            else:
                print_result(False, f"Upload failed with status {response.status_code}: {response.text}")
                return None
                
    except Exception as e:
        print_result(False, f"Upload failed with exception: {e}")
        return None


def test_wait_for_indexing(document_id, max_wait=60):
    """Test 3: Wait for Document Indexing"""
    print_test_header("Wait for Document Indexing")
    
    if not document_id:
        print_result(False, "No document ID provided")
        return None
    
    try:
        print(f"Waiting for document {document_id} to be indexed...")
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            response = requests.get(f"{API_BASE}/documents", timeout=10)
            
            if response.status_code == 200:
                documents = response.json().get("documents", [])
                
                # Find our document
                target_doc = None
                for doc in documents:
                    if doc.get("id") == document_id:
                        target_doc = doc
                        break
                
                if target_doc:
                    status = target_doc.get("status")
                    total_chunks = target_doc.get("total_chunks", 0)
                    
                    print(f"Current status: {status}, chunks: {total_chunks}")
                    
                    if status == "indexed":
                        print(f"Document details: {json.dumps(target_doc, indent=2, default=str)}")
                        print_result(True, f"Document indexed successfully with {total_chunks} chunks")
                        return target_doc
                    elif status == "error":
                        error_msg = target_doc.get("error_message", "Unknown error")
                        print_result(False, f"Document indexing failed: {error_msg}")
                        return None
                    
                else:
                    print_result(False, f"Document {document_id} not found in document list")
                    return None
            
            time.sleep(5)  # Wait 5 seconds before checking again
        
        print_result(False, f"Document indexing timed out after {max_wait} seconds")
        return None
        
    except Exception as e:
        print_result(False, f"Error waiting for indexing: {e}")
        return None


def test_stats():
    """Test 4: Check System Stats"""
    print_test_header("System Stats")
    
    try:
        response = requests.get(f"{API_BASE}/chat/stats", timeout=10)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            stats = response.json()
            print(f"System stats: {json.dumps(stats, indent=2)}")
            
            total_docs = stats.get("total_documents", 0)
            total_chunks = stats.get("total_chunks", 0)
            
            if total_docs > 0 and total_chunks > 0:
                print_result(True, f"Stats look good: {total_docs} documents, {total_chunks} chunks")
                return True
            else:
                print_result(False, f"Stats show no documents or chunks: docs={total_docs}, chunks={total_chunks}")
                return False
        else:
            print_result(False, f"Stats request failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print_result(False, f"Stats request failed with exception: {e}")
        return False


def test_chat_question(question, test_number):
    """Test chat functionality with a legal question"""
    print_test_header(f"Legal Question {test_number}")
    
    try:
        payload = {
            "question": question,
            "max_sources": 5
        }
        
        print(f"Asking question: {question}")
        
        response = requests.post(f"{API_BASE}/chat", json=payload, timeout=30)
        print(f"Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            answer = result.get("answer", "")
            sources = result.get("sources", [])
            processing_time = result.get("processing_time", 0)
            chunks_retrieved = result.get("chunks_retrieved", 0)
            
            print(f"Processing time: {processing_time:.2f}s")
            print(f"Chunks retrieved: {chunks_retrieved}")
            print(f"Sources found: {len(sources)}")
            
            print(f"\nAnswer: {answer}")
            
            if sources:
                print("\nSources:")
                for i, source in enumerate(sources, 1):
                    print(f"  {i}. {source.get('title', 'Unknown')} - {source.get('author', 'Unknown')} ({source.get('year', 'N/A')})")
                    print(f"     Relevance: {source.get('relevance_score', 0):.3f}")
                    if source.get('page'):
                        print(f"     Page: {source.get('page')}")
                    print(f"     Text: {source.get('chunk_text', '')[:100]}...")
                    print()
            
            if answer and len(answer) > 10:  # Basic check for meaningful answer
                if sources and len(sources) > 0:
                    print_result(True, f"Question answered successfully with {len(sources)} sources")
                    return True
                else:
                    print_result(False, "Answer received but no sources provided")
                    return False
            else:
                print_result(False, "Empty or too short answer received")
                return False
                
        else:
            print_result(False, f"Chat request failed with status {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print_result(False, f"Chat request failed with exception: {e}")
        return False


def main():
    """Run all backend tests"""
    print("JuristaAI Backend API Tests")
    print(f"Testing API at: {API_BASE}")
    print(f"Test PDF: {TEST_PDF_PATH}")
    
    results = {}
    
    # Test 1: Health Check
    results['health_check'] = test_health_check()
    
    # Test 2: Document Upload
    document_id = test_document_upload()
    results['document_upload'] = document_id is not None
    
    # Test 3: Wait for Indexing
    indexed_doc = None
    if document_id:
        indexed_doc = test_wait_for_indexing(document_id)
        results['document_indexing'] = indexed_doc is not None
    else:
        results['document_indexing'] = False
        print_test_header("Wait for Document Indexing")
        print_result(False, "Skipped - no document to index")
    
    # Test 4: System Stats
    results['system_stats'] = test_stats()
    
    # Test 5 & 6: Chat Questions
    for i, question in enumerate(TEST_QUESTIONS, 1):
        test_key = f'chat_question_{i}'
        results[test_key] = test_chat_question(question, i)
    
    # Summary
    print_test_header("Test Summary")
    
    total_tests = len(results)
    passed_tests = sum(1 for result in results.values() if result)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nOverall: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())