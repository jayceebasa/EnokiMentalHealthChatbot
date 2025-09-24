#!/usr/bin/env python3
"""
Test script to verify Gemini + RoBERTa API integration
"""
import os
import sys
import requests
import json
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'enoki.settings')

try:
    import django
    django.setup()
    from core.gemini_client import generate_reply
    print("✅ Django and Gemini client imported successfully")
except Exception as e:
    print(f"❌ Failed to import Django/Gemini: {e}")
    sys.exit(1)

# Configuration
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

def test_roberta_api():
    """Test RoBERTa emotion detection API"""
    print("\n🧪 Testing RoBERTa API...")
    
    test_text = "I'm feeling really anxious about my upcoming exam, but also excited to show what I've learned."
    
    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/predict_all", 
            json={"text": test_text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ RoBERTa API working!")
        print(f"   Text: {test_text}")
        print(f"   Top emotions:")
        for emotion in data['emotions'][:3]:  # Show top 3
            print(f"   - {emotion['label']}: {emotion['score']:.3f}")
        print(f"   Sarcasm: {data['sarcasm']} (score: {data['sarcasm_score']:.3f})")
        
        return data['emotions']
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to RoBERTa API at {AI_SERVICE_URL}")
        print("   Make sure the AI service is running (docker-compose up)")
        return None
    except Exception as e:
        print(f"❌ RoBERTa API error: {e}")
        return None

def test_gemini_api():
    """Test Gemini API directly"""
    print("\n🧪 Testing Gemini API...")
    
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY not found in environment")
        return False
        
    test_text = "I'm feeling overwhelmed with work"
    test_emotions = [
        {"label": "stress", "score": 0.8},
        {"label": "anxiety", "score": 0.6}
    ]
    test_preferences = {"tone": "empathetic", "language": "en"}
    
    try:
        reply = generate_reply(test_text, test_emotions, test_preferences)
        print(f"✅ Gemini API working!")
        print(f"   Input: {test_text}")
        print(f"   Response: {reply[:100]}{'...' if len(reply) > 100 else ''}")
        return True
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return False

def test_integration():
    """Test full integration: RoBERTa → Gemini"""
    print("\n🧪 Testing Full Integration...")
    
    test_text = "Today has been absolutely terrible. I got fired, my car broke down, and now it's raining. Just perfect."
    
    # Step 1: Get emotions from RoBERTa
    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/predict_all", 
            json={"text": test_text},
            timeout=30
        )
        response.raise_for_status()
        roberta_data = response.json()
        emotions = roberta_data['emotions']
        
        print(f"✅ Step 1 - RoBERTa analysis complete")
        print(f"   Sarcasm detected: {roberta_data['sarcasm']} ({roberta_data['sarcasm_score']:.3f})")
        
    except Exception as e:
        print(f"❌ Step 1 failed - RoBERTa error: {e}")
        return False
    
    # Step 2: Generate response with Gemini
    try:
        preferences = {"tone": "empathetic", "language": "en"}
        reply = generate_reply(test_text, emotions, preferences)
        
        print("✅ Step 2 - Gemini response generated")
        print("✅ FULL INTEGRATION SUCCESS!")
        print("\n📝 Complete Flow:")
        print(f"   User: {test_text}")
        emotions_str = ", ".join([f"{e['label']}({e['score']:.2f})" for e in emotions[:3]])
        print(f"   RoBERTa Emotions: {emotions_str}")
        print(f"   Sarcasm: {roberta_data['sarcasm']}")
        print(f"   Gemini Reply: {reply}")
        
        return True
        
    except Exception as e:
        print(f"❌ Step 2 failed - Gemini error: {e}")
        return False

def main():
    print("🚀 Testing Gemini + RoBERTa Integration")
    print("=" * 50)
    
    # Test each component
    emotions = test_roberta_api()
    gemini_works = test_gemini_api()
    
    if emotions and gemini_works:
        integration_works = test_integration()
        
        if integration_works:
            print("\n" + "=" * 50)
            print("🎉 ALL TESTS PASSED!")
            print("Your Gemini + RoBERTa integration is working perfectly!")
        else:
            print("\n❌ Integration test failed")
    else:
        print("\n❌ Component tests failed - cannot test integration")
    
if __name__ == "__main__":
    main()