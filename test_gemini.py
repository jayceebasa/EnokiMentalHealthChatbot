# test_gemini.py - Simple Gemini API test
import os
from dotenv import load_dotenv

print("Testing Gemini API connection...")
print("=" * 40)

# Load environment variables from .env file
print("🔄 Loading .env file...")
load_dotenv()
print("✅ .env file loaded")

# Check if API key is set
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("❌ GEMINI_API_KEY environment variable not set!")
    print("   Please set your Gemini API key:")
    print("   export GEMINI_API_KEY='your-api-key-here'")
    exit(1)

print(f"✅ API key found: {api_key[:10]}...")

# Test imports
try:
    print("\n🔄 Testing imports...")
    import google.generativeai as genai
    print("✅ google-generativeai imported successfully")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("   Run: pip install google-generativeai")
    exit(1)

# Test API configuration and call
try:
    print("🔄 Configuring Gemini...")
    genai.configure(api_key=api_key)
    
    # First, list available models
    print("🔄 Getting available models...")
    models = genai.list_models()
    available_models = []
    
    for model in models:
        if 'generateContent' in model.supported_generation_methods:
            available_models.append(model.name)
            print(f"   ✅ Available: {model.name}")
    
    if not available_models:
        print("❌ No models support generateContent")
        exit(1)
    
    # Use the first available model
    model_name = available_models[0]
    print(f"🔄 Using model: {model_name}")
    model = genai.GenerativeModel(model_name)
    
    print("🔄 Testing API call...")
    response = model.generate_content("Say 'Hello, Gemini is working!' and nothing else.")
    
    if hasattr(response, "text") and response.text:
        print(f"✅ Success! Gemini responded: {response.text.strip()}")
    else:
        print(f"⚠️  Got response but no text: {response}")
        
except Exception as e:
    print(f"❌ Gemini API call failed: {e}")
    exit(1)

print("\n" + "=" * 40)
print("🎉 Gemini is working correctly!")