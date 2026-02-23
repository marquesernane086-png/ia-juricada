#!/usr/bin/env python3
"""
JuristaAI Backend Testing - Specific Review Request Test
Test the exact 3-step scenario requested:
1. Upload specific PDF with metadata
2. Poll for indexing completion 
3. Ask specific question and verify response
"""

import requests
import time
import json
import os

# Backend URL
BASE_URL = "https://juristico-ia.preview.emergentagent.com/api"

def test_document_upload():
    """Step 1: Upload the test PDF with specific metadata"""
    print("=== STEP 1: Document Upload Test ===")
    
    file_path = "/app/backend/data/uploads/test_legal_book.pdf"
    
    # Check if file exists
    if not os.path.exists(file_path):
        print(f"❌ Test file not found: {file_path}")
        return None
    
    print(f"✅ Found test file: {file_path}")
    
    # Prepare multipart form data as specified in the request
    upload_data = {
        'title': 'Curso de Direito Civil Brasileiro',
        'author': 'Carlos Roberto Goncalves', 
        'year': '2018',
        'legal_subject': 'Direito Civil'
    }
    
    try:
        with open(file_path, 'rb') as pdf_file:
            files = {'file': ('test_legal_book.pdf', pdf_file, 'application/pdf')}
            
            print(f"Uploading to: {BASE_URL}/documents/upload")
            print(f"Upload data: {upload_data}")
            
            response = requests.post(
                f"{BASE_URL}/documents/upload",
                files=files,
                data=upload_data,
                timeout=30
            )
            
            print(f"Upload response status: {response.status_code}")
            print(f"Upload response headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ Upload successful!")
                print(f"Document ID: {result.get('id')}")
                print(f"Status: {result.get('status')}")
                print(f"Full response: {json.dumps(result, indent=2)}")
                return result.get('id')
            else:
                print(f"❌ Upload failed with status {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        return None

def test_indexing_poll(document_id):
    """Step 2: Poll GET /api/documents every 10s until status is indexed (max 120s)"""
    print("\n=== STEP 2: Indexing Status Polling ===")
    
    if not document_id:
        print("❌ No document ID provided, skipping indexing test")
        return False
    
    max_wait_time = 120  # 120 seconds as specified
    poll_interval = 10   # 10 seconds as specified
    start_time = time.time()
    
    print(f"Polling for document indexing completion (max {max_wait_time}s, every {poll_interval}s)")
    
    while time.time() - start_time < max_wait_time:
        try:
            response = requests.get(f"{BASE_URL}/documents", timeout=10)
            
            if response.status_code == 200:
                documents = response.json()
                print(f"Retrieved {len(documents)} documents")
                
                # Find our document
                target_doc = None
                for doc in documents:
                    if doc.get('id') == document_id:
                        target_doc = doc
                        break
                
                if target_doc:
                    status = target_doc.get('indexing_status', 'unknown')
                    print(f"Document status: {status}")
                    
                    if status == 'indexed':
                        elapsed_time = time.time() - start_time
                        print(f"✅ Document indexing completed in {elapsed_time:.1f} seconds")
                        print(f"Document details: {json.dumps(target_doc, indent=2)}")
                        return True
                    elif status in ['processing', 'pending']:
                        print(f"⏳ Still indexing... ({status})")
                    else:
                        print(f"⚠️ Unexpected status: {status}")
                else:
                    print(f"❌ Document with ID {document_id} not found in documents list")
            else:
                print(f"❌ Failed to retrieve documents: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Polling error: {str(e)}")
        
        if time.time() - start_time < max_wait_time:
            print(f"Waiting {poll_interval}s before next poll...")
            time.sleep(poll_interval)
    
    print(f"❌ Indexing timeout after {max_wait_time}s")
    return False

def test_chat_question():
    """Step 3: Ask specific question with max_sources=5"""
    print("\n=== STEP 3: Chat Question Test ===")
    
    question_data = {
        "question": "O que é responsabilidade civil objetiva?",
        "max_sources": 5
    }
    
    print(f"Asking question: {question_data['question']}")
    print(f"Max sources requested: {question_data['max_sources']}")
    
    try:
        start_time = time.time()
        
        response = requests.post(
            f"{BASE_URL}/chat",
            json=question_data,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        
        response_time = time.time() - start_time
        print(f"Response time: {response_time:.2f} seconds")
        print(f"Chat response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            
            answer = result.get('answer', '')
            sources = result.get('sources', [])
            
            # Print first 300 chars of answer as requested
            print(f"✅ Chat response received!")
            print(f"Answer (first 300 chars): {answer[:300]}...")
            print(f"Number of sources: {len(sources)}")
            
            # Additional details
            print(f"\nFull response metadata:")
            print(f"- Answer length: {len(answer)} characters")
            print(f"- Sources count: {len(sources)}")
            print(f"- Processing time: {result.get('processing_time', 'N/A')} seconds")
            print(f"- Chunks retrieved: {result.get('chunks_retrieved', 'N/A')}")
            
            # Show source details
            if sources:
                print(f"\nSource details:")
                for i, source in enumerate(sources, 1):
                    relevance = source.get('relevance_score', 'N/A')
                    page = source.get('page_number', 'N/A')
                    text_preview = source.get('text', '')[:100]
                    print(f"  {i}. Relevance: {relevance}, Page: {page}, Text: {text_preview}...")
            
            return True
        else:
            print(f"❌ Chat request failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Chat error: {str(e)}")
        return False

def main():
    """Run the complete 3-step test sequence"""
    print("JuristaAI Quick Test - 3 Step Verification")
    print("=" * 50)
    
    # Step 1: Upload document
    document_id = test_document_upload()
    
    # Step 2: Wait for indexing
    if document_id:
        indexing_success = test_indexing_poll(document_id)
    else:
        indexing_success = False
    
    # Step 3: Ask question (run regardless of indexing status to test system)
    chat_success = test_chat_question()
    
    # Summary
    print("\n" + "=" * 50)
    print("QUICK TEST SUMMARY:")
    print(f"1. Document Upload: {'✅ PASS' if document_id else '❌ FAIL'}")
    print(f"2. Indexing Status: {'✅ PASS' if indexing_success else '❌ FAIL'}")
    print(f"3. Chat Question:   {'✅ PASS' if chat_success else '❌ FAIL'}")
    
    overall_success = all([document_id is not None, indexing_success, chat_success])
    print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    return overall_success

if __name__ == "__main__":
    main()