#!/usr/bin/env python3
"""
Simple test to verify RoBERTa API and Gemini integration components
"""
import requests
import os
import json

# Test configuration
AI_SERVICE_URL = "http://127.0.0.1:8001"
GEMINI_API_KEY = "AIzaSyCnFMYoTu2XgBTLJTKFcHTB43Q8mqWH6xU"

def test_roberta_api():
    """Test RoBERTa emotion detection API"""
    print("🧪 Testing RoBERTa API...")
    
    test_text = "I'm feeling really anxious about my upcoming exam, but also excited to show what I've learned."
    
    try:
        response = requests.post(
            f"{AI_SERVICE_URL}/predict_all", 
            json={"text": test_text},
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print("✅ RoBERTa API working!")
        print(f"   Text: {test_text}")
        print("   Top emotions:")
        for emotion in data['emotions'][:3]:
            print(f"   - {emotion['label']}: {emotion['score']:.3f}")
        print(f"   Sarcasm: {data['sarcasm']} (score: {data['sarcasm_score']:.3f})")
        
        return data['emotions'], data
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to RoBERTa API at {AI_SERVICE_URL}")
        print("   Make sure the AI service is running (docker-compose up)")
        return None, None
    except Exception as e:
        print(f"❌ RoBERTa API error: {e}")
        return None, None

def test_gemini_api():
    """Test Gemini API configuration"""
    print("\n🧪 Testing Gemini API...")
    
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_API_KEY_HERE":
        print("❌ GEMINI_API_KEY not properly configured")
        return False
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Simple test
        response = model.generate_content("Say hello in a supportive way for mental health support")
        print("✅ Gemini API working!")
        print(f"   Test response: {response.text[:100]}...")
        return True
        
    except Exception as e:
        print(f"❌ Gemini API error: {e}")
        return False

def test_integration_flow():
    """Test the integration flow"""
    print("\n🧪 Testing Integration Flow...")
    
    test_text = "I had such a wonderful day today. My car broke down, I got fired, and it started raining. Absolutely perfect!"
    
    # Step 1: RoBERTa analysis
    emotions, roberta_data = test_roberta_api()
    if not emotions:
        return False
    
    # Step 2: Simulate Gemini processing
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        # Create prompt similar to what Django view would create
        top_emotions = emotions[:5]  # Top 5 emotions
        emotions_summary = ", ".join([f"{e['label']} ({e['score']:.2f})" for e in top_emotions])
        
        prompt = f"""
        The user said: "{test_text}"
        
        Detected emotions: {emotions_summary}
        Sarcasm detection: {roberta_data['sarcasm']} (confidence: {roberta_data['sarcasm_score']:.2f})
        
        Respond as a supportive, empathetic mental health companion. 
        Keep the response concise but caring.
        """
        
        response = model.generate_content(prompt)
        
        print("✅ Integration flow successful!")
        print("\n📝 Complete Integration Test:")
        print(f"   User Input: {test_text}")
        print(f"   RoBERTa Emotions: {emotions_summary}")
        print(f"   Sarcasm: {roberta_data['sarcasm']} ({roberta_data['sarcasm_score']:.2f})")
        print(f"   Gemini Response: {response.text}")
        
        return True
        
    except Exception as e:
        print(f"❌ Integration flow error: {e}")
        return False

def main():
    print("🚀 Testing Gemini + RoBERTa Integration")
    print("=" * 50)
    
    # Test individual components
    emotions, roberta_data = test_roberta_api()
    gemini_works = test_gemini_api()
    
    if emotions and gemini_works:
        integration_success = test_integration_flow()
        
        print("\n" + "=" * 50)
        if integration_success:
            print("🎉 ALL TESTS PASSED!")
            print("Your Gemini + RoBERTa integration is working!")
            print("\nNext steps:")
            print("1. Start Django server: python manage.py runserver")
            print("2. Visit http://localhost:8000/chat/ to test the web interface")
        else:
            print("❌ Integration test failed")
    else:
        print("\n❌ Component tests failed")
        if not emotions:
            print("- RoBERTa API is not accessible")
        if not gemini_works:
            print("- Gemini API is not working")

if __name__ == "__main__":
    main()