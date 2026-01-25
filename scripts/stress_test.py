
import time
import json
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from concurrent.futures import ThreadPoolExecutor
from app.conversation.controller import handle_user_text, detect_intent
from app.conversation.state import ConversationState
from app.rag.retriever import Retriever

# 20 Common ITS Questions
QUESTIONS = [
    "How do I connect to the VPN?",
    "I forgot my password, how do I reset it?",
    "How do I set up MFA on my phone?",
    "What is the WiFi password for the guest network?",
    "I can't access my email.",
    "How do I install Office 365?",
    "Where can I find the help desk?",
    "My computer is slow.",
    "How do I print from my laptop?",
    "What is the URL for Sakai?",
    "How do I access Zoom?",
    "Can I get Adobe Creative Cloud?",
    "How do I report a phishing email?",
    "My internet is not working.",
    "How do I connect to the eduroam wifi?",
    "What software is available for students?",
    "How do I submit a ticket?",
    "My account is locked.",
    "How do I change my MFA settings?",
    "Is there a VPN for Linux?"
]

def run_test_query(query, retriever, index):
    state = ConversationState(session_id=f"stress-test-{index}")
    
    start_time = time.time()
    result = handle_user_text(state, query, retriever)
    duration = time.time() - start_time
    
    return {
        "query": query,
        "intent": result["intent"],
        "sources": len(result["sources"]),
        "response_length": len(result["response"]),
        "duration": duration,
        "response_preview": result["response"][:100].replace("\n", " ") + "..."
    }

def main():
    print("Loading RAG Retriever...")
    retriever = Retriever()
    print("Retriever loaded.")
    
    results = []
    print(f"Starting stress test with {len(QUESTIONS)} questions...")
    
    # Run sequentially to not overload local LLM (Ollama)
    for i, q in enumerate(QUESTIONS):
        print(f"Processing ({i+1}/{len(QUESTIONS)}): {q}")
        try:
            res = run_test_query(q, retriever, i)
            results.append(res)
            print(f"  -> Returned {res['sources']} sources in {res['duration']:.2f}s")
        except Exception as e:
            print(f"  -> ERROR: {e}")
            results.append({"query": q, "error": str(e)})

    print("\n" + "="*80)
    print(f"{'#':<3} | {'Query':<40} | {'Intent':<12} | {'Srcs':<4} | {'Time':<6} | {'Response Preview'}")
    print("="*80)
    
    total_time = 0
    success_count = 0
    
    for i, r in enumerate(results):
        if "error" in r:
            print(f"{i+1:<3} | {r['query']:<40} | ERROR        | -    | -      | {r['error']}")
        else:
            success_count += 1
            total_time += r["duration"]
            print(f"{i+1:<3} | {r['query'][:40]:<40} | {r['intent']:<12} | {r['sources']:<4} | {r['duration']:.2f}s | {r['response_preview']}")
            
    print("="*80)
    print(f"Total Questions: {len(QUESTIONS)}")
    print(f"Successful:      {success_count}")
    print(f"Failed:          {len(results) - success_count}")
    if success_count > 0:
        print(f"Avg Latency:     {total_time / success_count:.2f}s")
    print("="*80)

if __name__ == "__main__":
    main()
