# # agent.py

# import os
# import json
# import pickle
# import numpy as np
# import pandas as pd
# import faiss
# import requests
# import time
# import re
# from datetime import datetime, timedelta
# from typing import List, Dict, Any, Optional
# from sentence_transformers import SentenceTransformer

# # ============================================================================
# # API KEY ROTATION MANAGER
# # ============================================================================

# class APIKeyRotator:
#     """Manages multiple API keys with automatic rotation and error handling"""
    
#     def __init__(self, api_keys: List[str], cooldown_minutes: int = 5):
#         """
#         Initialize key rotator
        
#         Args:
#             api_keys: List of OpenRouter API keys
#             cooldown_minutes: Minutes to wait before retrying a failed key
#         """
#         self.api_keys = api_keys
#         self.current_index = 0
#         self.cooldown_minutes = cooldown_minutes
        
#         # Track failed keys: {key: datetime_of_failure}
#         self.failed_keys = {}
        
#         # Rate limit error codes (429: Too Many Requests, 402: Payment Required/Quota Exceeded, 503: Service Unavailable)
#         self.rate_limit_codes = [429, 402, 503]
        
#         print(f"🔑 Key Rotator initialized with {len(api_keys)} keys")
    
#     def get_next_key(self) -> Optional[str]:
#         """Get next available API key, skipping failed ones"""
        
#         # Clean up expired cooldowns
#         now = datetime.now()
#         expired = [k for k, fail_time in self.failed_keys.items() 
#                      if now - fail_time > timedelta(minutes=self.cooldown_minutes)]
#         for k in expired:
#             del self.failed_keys[k]
#             print(f"✅ Key {self._mask_key(k)} cooldown expired, back in rotation")
        
#         # Try to find an available key
#         attempts = 0
#         max_attempts = len(self.api_keys)
        
#         while attempts < max_attempts:
#             key = self.api_keys[self.current_index]
            
#             # Move to next key for next call
#             self.current_index = (self.current_index + 1) % len(self.api_keys)
            
#             # Check if key is available
#             if key not in self.failed_keys:
#                 return key
            
#             attempts += 1
        
#         # All keys failed
#         print("⚠️ All API keys are in cooldown!")
#         return None
    
#     def mark_key_failed(self, key: str, error_code: int = None):
#         """Mark a key as failed (rate limited)"""
#         if error_code in self.rate_limit_codes:
#             self.failed_keys[key] = datetime.now()
#             print(f"❌ Key {self._mask_key(key)} marked as failed (code: {error_code})")
#             print(f"   Cooldown: {self.cooldown_minutes} minutes")
    
#     def _mask_key(self, key: str) -> str:
#         """Mask API key for logging"""
#         if len(key) > 10:
#             return f"{key[:7]}...{key[-4:]}"
#         return "***"
    
#     def get_status(self) -> Dict[str, Any]:
#         """Get current rotation status"""
#         total = len(self.api_keys)
#         failed = len(self.failed_keys)
#         available = total - failed
        
#         # Check if index is valid before masking key
#         next_key_masked = self._mask_key(self.api_keys[self.current_index]) if self.api_keys else "N/A"
        
#         return {
#             'total_keys': total,
#             'available_keys': available,
#             'failed_keys': failed,
#             'current_index': self.current_index,
#             'next_key': next_key_masked
#         }

# # ============================================================================
# # ENHANCED LLM INTERFACE WITH KEY ROTATION
# # ============================================================================

# class OpenRouterLLM:
#     """Generic OpenRouter LLM interface with key rotation"""
    
#     def __init__(self, key_rotator: APIKeyRotator, model: str, role: str = "LLM"):
#         self.key_rotator = key_rotator
#         self.model = model
#         self.role = role
#         self.url = "https://openrouter.ai/api/v1/chat/completions"
#         print(f"🤖 {role} initialized: {model}")
    
#     def generate(self, system_prompt: str, user_prompt: str, 
#                      max_tokens: int = 1500, temperature: float = 0.7,
#                      max_retries: int = 3) -> str:
#         """Generate response with automatic key rotation"""
        
#         for attempt in range(max_retries):
#             # Get next available key
#             api_key = self.key_rotator.get_next_key()
            
#             if api_key is None:
#                 # Raise a custom error instead of returning a string, allowing main.py to catch it
#                 raise ConnectionError(f"❌ {self.role} Error: All API keys exhausted. Please wait {self.key_rotator.cooldown_minutes} minutes.")
            
#             try:
#                 headers = {
#                     "Authorization": f"Bearer {api_key}",
#                     "Content-Type": "application/json",
#                     "HTTP-Referer": "https://github.com/agri-agent",
#                     "X-Title": "AgriAgent"
#                 }
                
#                 payload = {
#                     "model": self.model,
#                     "messages": [
#                         {"role": "system", "content": system_prompt},
#                         {"role": "user", "content": user_prompt}
#                     ],
#                     "temperature": temperature,
#                     "max_tokens": max_tokens
#                 }
                
#                 # Use a slightly longer timeout for robust requests
#                 response = requests.post(self.url, headers=headers, json=payload, timeout=90)
                
#                 # Check for rate limit errors
#                 if response.status_code in self.key_rotator.rate_limit_codes:
#                     self.key_rotator.mark_key_failed(api_key, response.status_code)
#                     print(f"⚠️ {self.role}: Rate limit hit, trying next key (attempt {attempt+1}/{max_retries})")
#                     time.sleep(1) # Small delay before checking next key
#                     continue
                
#                 response.raise_for_status()
#                 result = response.json()
#                 return result["choices"][0]["message"]["content"]
            
#             except requests.exceptions.RequestException as e:
#                 error_msg = str(e)
                
#                 # Check if it's a rate limit error in exception text
#                 if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
#                     self.key_rotator.mark_key_failed(api_key, 429)
#                     print(f"⚠️ {self.role}: Rate limit detected in error, trying next key")
#                     time.sleep(1) # Small delay before checking next key
#                     continue
                
#                 # Other errors
#                 if attempt == max_retries - 1:
#                     # Raise for non-rate-limit errors on final attempt
#                     raise RuntimeError(f"❌ {self.role} Error: Max retries exceeded. Last error: {error_msg}") from e
                
#                 print(f"⚠️ {self.role}: Connection/API error on attempt {attempt+1}, retrying...")
#                 time.sleep(3) # Longer wait for generic errors
        
#         # Should be unreachable, but good practice
#         raise RuntimeError(f"❌ {self.role} Error: Max retries exceeded")


# class AgentLLM(OpenRouterLLM):
#     """Mistral LLM for agent decision-making"""
    
#     def __init__(self, key_rotator: APIKeyRotator, model: str):
#         super().__init__(key_rotator, model, role="Agent LLM (Mistral)")
    
#     def decide_tools(self, question: str) -> Dict[str, bool]:
#         """Use LLM to decide which tools to call"""
#         system_prompt = """You are a tool selection agent. Given a farmer's question, decide which tools to use.

# Available tools:
# - RAG: Static agriculture knowledge (crop practices, cultivation, soil, etc.)
# - Weather: Live weather data (temperature, humidity, rainfall, wind)
# - Market: Commodity prices and market rates
# - Water: Soil moisture, groundwater, irrigation data
# - Pest: Pest and disease management advice

# Output ONLY a JSON object with true/false for each tool. Output must be valid JSON and contain ONLY the keys listed.

# {
#     "rag": true/false,
#     "weather": true/false,
#     "market": true/false,
#     "water": true/false,
#     "pest": true/false
# }

# Rules:
# - ALWAYS set "rag": true (we always search RAG first)
# - Set other tools to true only if specifically needed
# - Be conservative - don't call unnecessary tools"""
        
#         user_prompt = f"Question: {question}\n\nWhich tools should be used? Return JSON only."
        
#         try:
#             response = self.generate(system_prompt, user_prompt, max_tokens=200, temperature=0.3)
            
#             # --- Robust JSON Extraction and Parsing ---
            
#             # 1. Clean response by removing non-JSON characters/text
#             json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
#             if json_match:
#                 json_string = json_match.group().strip()
                
#                 # 2. Attempt to parse JSON
#                 decisions = json.loads(json_string)
                
#                 # 3. Ensure keys are correct and enforce RAG rule
#                 allowed_keys = ['rag', 'weather', 'market', 'water', 'pest']
#                 final_decisions = {k: decisions.get(k, False) for k in allowed_keys}
#                 final_decisions['rag'] = True 
                
#                 return final_decisions
#             else:
#                 raise ValueError(f"No valid JSON found in LLM response: {response[:100]}...")

#         except Exception as e:
#             # Catch LLM errors (rate limit, connection, parsing failure)
#             print(f"⚠️ Agent LLM tool decision error: {e}. Using keyword fallback.")
#             # Fallback must be absolutely safe
#             return self._fallback_detection(question)
    
#     def _fallback_detection(self, question: str) -> Dict[str, bool]:
#         """Fallback keyword-based tool detection"""
#         q = question.lower()
#         return {
#             'rag': True, # Always true
#             'weather': any(w in q for w in ['weather', 'temperature', 'rain', 'climate', 'humidity', 'wind']),
#             'market': any(w in q for w in ['price', 'market', 'cost', 'rate', 'selling', 'commodity']),
#             'water': any(w in q for w in ['water', 'irrigation', 'moisture', 'rainfall', 'groundwater']),
#             'pest': any(w in q for w in ['pest', 'disease', 'insect', 'fungal', 'virus', 'infection'])
#         }


# class ResponseGeneratorLLM(OpenRouterLLM):
#     """Separate LLM for generating final farmer-facing responses"""
    
#     def __init__(self, key_rotator: APIKeyRotator, model: str):
#         super().__init__(key_rotator, model, role="Response Generator LLM (Gemini/Flash)")


# # ============================================================================
# # TOOL CLASSES
# # ============================================================================

# class RAGTool:
#     """Searches the FAISS vector database for agriculture knowledge"""
    
#     def __init__(self, index_path: str, metadata_path: str):
#         print("📚 Loading RAG Tool...")
#         # CRITICAL: Set trust_remote_code=False for security if running locally, 
#         # but keep as is if this environment requires it for model loading.
#         self.model = SentenceTransformer("all-mpnet-base-v2") 
#         self.index = faiss.read_index(index_path)
        
#         with open(metadata_path, 'rb') as f:
#             data = pickle.load(f)
#             self.documents = data['documents']
#             self.metadata = data['metadata']
        
#         print(f"✅ RAG Tool loaded with {self.index.ntotal} vectors")
    
#     def search(self, query: str, k: int = 3, threshold: float = 0.35) -> Dict[str, Any]:
#         try:
#             query_embedding = self.model.encode([query]).astype('float32')
            
#             # --- FAISS Search (Vector is normalized after encoding) ---
#             query_embedding = query_embedding / np.linalg.norm(query_embedding)
#             distances, indices = self.index.search(query_embedding, k)
            
#             # Convert distance (squared Euclidean distance for normalized vectors) to similarity
#             # Sim = 1 - (dist^2) / 2 is the exact cosine similarity for L2-normalized vectors
#             similarities = 1 - (distances[0] ** 2) / 2
            
#             results = []
#             scores = []
            
#             for idx, score in zip(indices[0], similarities):
#                 # Check for valid index and threshold
#                 if score >= threshold and 0 <= idx < len(self.documents):
#                     results.append({
#                         'text': self.documents[idx],
#                         'source': self.metadata[idx]['source'],
#                         'type': self.metadata[idx]['type']
#                     })
#                     scores.append(float(score))
            
#             is_relevant = len(results) > 0 and (max(scores) if scores else 0.0) >= threshold
            
#             return {
#                 'success': True,
#                 'results': results,
#                 'scores': scores,
#                 'is_relevant': is_relevant,
#                 'top_score': max(scores) if scores else 0.0
#             }
        
#         except Exception as e:
#             # Added more context to the error message
#             print(f"❌ RAGTool search error: {e}")
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'is_relevant': False
#             }


# class WeatherTool:
#     """Fetches live weather data for Telangana cities"""
    
#     def __init__(self, api_key: str):
#         self.api_key = api_key
#         self.base_url = "http://api.openweathermap.org/data/2.5/weather"
#         print("🌦️ Weather Tool initialized")
    
#     def get_weather(self, city: str = "Hyderabad") -> Dict[str, Any]:
#         try:
#             params = {
#                 'q': f"{city},IN",
#                 'appid': self.api_key,
#                 'units': 'metric'
#             }
            
#             response = requests.get(self.base_url, params=params, timeout=10)
#             response.raise_for_status()
#             data = response.json()
            
#             temp = data['main']['temp']
#             humidity = data['main']['humidity']
#             description = data['weather'][0]['description']
            
#             return {
#                 'success': True,
#                 'city': city,
#                 'temperature': temp,
#                 'humidity': humidity,
#                 'description': description,
#                 # --- Context Summary for LLM (Human Readable) ---
#                 'context_summary': (
#                     f"Live weather data for {city}, India: "
#                     f"Current conditions are '{description}'. "
#                     f"Temperature is {temp}°C, and humidity is {humidity}%. "
#                     f"Wind speed is {data['wind']['speed']} m/s."
#                 )
#             }
        
#         except Exception as e:
#             # Added key validation check
#             if '401' in str(e):
#                 error_msg = "Invalid OpenWeatherMap API key."
#             elif '404' in str(e):
#                 error_msg = f"City '{city}' not found."
#             else:
#                 error_msg = str(e)

#             return {
#                 'success': False,
#                 'error': error_msg,
#                 'city': city,
#                 'context_summary': f"Weather data for {city} is unavailable. Error: {error_msg}"
#             }


# class MarketPriceTool:
#     """Fetches commodity prices from local CSV data"""

#     # Define the mapping between tool-required columns and your CSV headers
#     COLUMN_MAPPING = {
#         'Date': 'DDate',
#         'Commodity': 'CommName',
#         'Market': 'YardName',
#         'Variety': 'VarityName',
#         'Min_Price': 'Minimum',
#         'Max_Price': 'Maximum',
#         'Modal_Price': 'Model'  # Added for completeness, if used later
#     }
    
#     def __init__(self, csv_path: str):
#         print("💰 Loading Market Price Tool...")
#         self.prices_df = None
#         self.csv_path = csv_path
        
#         try:
#             if not os.path.exists(csv_path):
#                 raise FileNotFoundError(f"CSV file not found at path: {csv_path}")
                
#             self.prices_df = pd.read_csv(csv_path)
            
#             # --- CRITICAL FIX: Rename columns here ---
#             # Create a reverse mapping for Pandas: {CSV_Header: Tool_Required_Name}
#             reverse_mapping = {v: k for k, v in self.COLUMN_MAPPING.items()}
            
#             # Filter the mapping to only rename columns that exist in the loaded CSV
#             columns_to_rename = {
#                 csv_col: tool_col 
#                 for csv_col, tool_col in reverse_mapping.items() 
#                 if csv_col in self.prices_df.columns
#             }
            
#             # Perform the renaming in place
#             self.prices_df.rename(columns=columns_to_rename, inplace=True)
#             # --- END CRITICAL FIX ---

#             # Check for the *newly renamed* required columns
#             required_cols = ['Commodity', 'Market', 'Variety', 'Min_Price', 'Max_Price', 'Date']
            
#             if not all(col in self.prices_df.columns for col in required_cols):
#                 print(f"⚠️ Warning: Market Price CSV missing some required columns AFTER RENAME: {required_cols}")
            
#             print(f"✅ Loaded {len(self.prices_df)} price records")
#         except Exception as e:
#             print(f"⚠️ Error loading market prices: {e}")
#             self.prices_df = None
    
#     # get_price method 
#     def get_price(self, commodity: str, market: Optional[str] = None) -> Dict[str, Any]:
#         if self.prices_df is None:
#             return {
#                 'success': False,
#                 'error': 'Market price data not available. Check file path.',
#                 'context_summary': 'Market price data is currently unavailable.'
#             }
        
#         try:
#             commodity_lower = commodity.lower()
            
#             # Filter rows where the commodity name (or related keyword) appears
#             matches = self.prices_df[
#                 self.prices_df.apply(
#                     # This correctly uses the renamed 'Commodity' column
#                     lambda row: commodity_lower in str(row).lower(), 
#                     axis=1
#                 )
#             ]
            
#             if len(matches) == 0:
#                 return {
#                     'success': False,
#                     'error': f'No price data found for {commodity}',
#                     'commodity': commodity,
#                     'context_summary': f'No recent market price data found for {commodity}.'
#                 }
            
#             price_records = matches.to_dict('records')
#             top_records = price_records[:5]
            
#             # --- Context Summary uses the correctly renamed columns ---
#             summary_lines = [f"Found {len(price_records)} market price records for {commodity.upper()}:"]
#             for record in top_records:
#                 try:
#                     line = (
#                         f"• {record.get('Market', 'N/A')} ({record.get('Date', 'N/A')}): "
#                         f"Variety: {record.get('Variety', 'N/A')}. "
#                         f"Price Range: ₹{record.get('Min_Price', 'N/A')} - ₹{record.get('Max_Price', 'N/A')}."
#                     )
#                     summary_lines.append(line)
#                 except Exception:
#                     summary_lines.append(f"• Price data record: {record}")
            
#             context_summary = "\n".join(summary_lines)
            
#             return {
#                 'success': True,
#                 'commodity': commodity,
#                 'records_found': len(price_records),
#                 'prices': top_records, 
#                 'context_summary': context_summary
#             }
        
#         except Exception as e:
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'context_summary': f'Error fetching market price data: {str(e)}'
#             }


# class WaterDataTool:
#     """Provides soil moisture, rainfall, and groundwater information (Mock Data)"""
    
#     def __init__(self):
#         print("💧 Water Data Tool initialized (using mock data)")
#         self.data = {
#             'telangana': {
#                 'avg_rainfall_mm': 850,
#                 'groundwater_level': 'Moderate (requires monitoring)',
#                 'soil_moisture': 'Medium (adequate for Kharif sowing)',
#                 'irrigation_advice': 'Use drip or micro-sprinkler irrigation systems for water conservation'
#             }
#         }
    
#     def get_water_info(self, region: str = "Telangana") -> Dict[str, Any]:
#         try:
#             region_data = self.data.get(region.lower(), self.data['telangana'])
            
#             # --- Context Summary for LLM (Human Readable) ---
#             context_summary = (
#                 f"Water & Irrigation Data for {region}: "
#                 f"Average annual rainfall: {region_data['avg_rainfall_mm']}mm. "
#                 f"Groundwater level status: {region_data['groundwater_level']}. "
#                 f"Current soil moisture: {region_data['soil_moisture']}. "
#                 f"Recommendation: {region_data['irrigation_advice']}."
#             )
            
#             return {
#                 'success': True,
#                 'region': region,
#                 'avg_rainfall_mm': region_data['avg_rainfall_mm'],
#                 'context_summary': context_summary
#             }
        
#         except Exception as e:
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'context_summary': f'Error fetching water data: {str(e)}'
#             }


# class PestAdvisoryTool:
#     """Provides pest and disease management advice (Mock Data)"""
    
#     def __init__(self):
#         print("🐛 Pest Advisory Tool initialized (using mock data)")
#         self.common_pests = {
#             'tomato': ['fruit borer', 'leaf curl virus', 'whitefly', 'early blight'],
#             'rice': ['stem borer', 'blast disease', 'brown planthopper (BPH)', 'sheath blight'],
#             'cotton': ['bollworm (pink/American)', 'whitefly', 'aphids', 'jassids'],
#             'wheat': ['rust', 'aphids', 'termites', 'loose smut']
#         }
    
#     def get_pest_info(self, crop: str) -> Dict[str, Any]:
#         try:
#             crop_lower = crop.lower()
#             pests = self.common_pests.get(crop_lower, [])
            
#             if pests:
#                 advice = (
#                     f"Common pests for {crop}: {', '.join(pests)}. "
#                     f"Use Integrated Pest Management (IPM) practices, including regular field scouting, "
#                     f"using resistant varieties, and only applying targeted pesticides when necessary. "
#                     f"Consult the local agricultural extension office for specific treatment protocols."
#                 )
#             else:
#                  advice = (
#                     f"No specific common pest list found for '{crop}'. "
#                     f"General advice: Monitor your crop for signs of pests or diseases, "
#                     f"maintain good field hygiene, and practice crop rotation."
#                 )
            
#             return {
#                 'success': True,
#                 'crop': crop,
#                 'common_pests': pests,
#                 'advice': advice,
#                 'context_summary': advice
#             }
        
#         except Exception as e:
#             return {
#                 'success': False,
#                 'error': str(e),
#                 'context_summary': f'Error fetching pest data: {str(e)}'
#             }


# # ============================================================================
# # MAIN AGRI-AGENT WITH KEY ROTATION
# # ============================================================================

# class AgriAgent:
#     """Agricultural Agent with multi-key rotation support"""
    
#     def __init__(
#         self,
#         openrouter_keys: List[str],
#         openweather_key: str,
#         faiss_index_path: str,
#         metadata_path: str,
#         market_prices_path: str,
#         response_llm_model: str,
#         agent_llm_model: str,
#         key_cooldown_minutes: int
#     ):
#         print("\n" + "="*70)
#         print("🌾 INITIALIZING AGRIAGENT WITH KEY ROTATION")
#         print("="*70 + "\n")
        
#         # Initialize key rotator
#         self.key_rotator = APIKeyRotator(openrouter_keys, key_cooldown_minutes)
        
#         # Initialize tools
#         self.rag_tool = RAGTool(faiss_index_path, metadata_path)
#         self.weather_tool = WeatherTool(openweather_key)
#         self.market_tool = MarketPriceTool(market_prices_path)
#         self.water_tool = WaterDataTool()
#         self.pest_tool = PestAdvisoryTool()
        
#         # Initialize dual LLMs with key rotator
#         print("\n📋 Dual LLM Architecture with Key Rotation:")
#         self.agent_llm = AgentLLM(self.key_rotator, agent_llm_model)
#         self.response_llm = ResponseGeneratorLLM(self.key_rotator, response_llm_model)
        
#         # System prompt for the final response LLM
#         self.response_system_prompt = """You are AgriAgent, an expert agricultural advisor for Indian farmers in Telangana.

# CRITICAL RULES:
# 1. Base your answer STRICTLY on the provided context data from RAG and other tools.
# 2. NEVER hallucinate or invent numbers—all data must come from the context.
# 3. If data is missing or a tool failed, clearly state the missing information (e.g., "Market price data is unavailable").
# 4. Keep responses clear, practical, and agriculture-focused.
# 5. Prioritize Indian farming practices and Telangana conditions.
# 6. Format the response to be easily readable, using paragraphs and bullet points where appropriate.

# RESPONSE STRUCTURE:
# Start with a direct, comprehensive answer. Follow with a detailed breakdown.
# """
        
#         print("\n" + "="*70)
#         print("✅ AGRIAGENT READY!")
#         print("="*70 + "\n")
    
#     def query(self, question: str, verbose: bool = False) -> Dict[str, Any]:
#         """Process farmer's question through the agent pipeline"""
        
#         if verbose:
#             print(f"\n{'='*70}")
#             print(f"❓ QUESTION: {question}")
#             print(f"{'='*70}\n")
            
#             status = self.key_rotator.get_status()
#             print(f"🔑 Key Status: {status['available_keys']}/{status['total_keys']} available")
        
#         tools_used = []
#         context_parts = []
        
#         # STEP 1: Agent LLM decides tools
#         if verbose:
#             print("\n🧠 Step 1: Agent LLM deciding tools...")
        
#         tool_decisions = self.agent_llm.decide_tools(question)
        
#         if verbose:
#             print(f"   Tools selected: {[k for k, v in tool_decisions.items() if v]}")
        
#         # STEP 2: Call RAG (Always run if successful)
#         rag_result = {'success': False, 'is_relevant': False}
#         if tool_decisions.get('rag', True):
#             if verbose:
#                 print("\n⚙️ Step 2: Calling RAG Tool...")
            
#             rag_result = self.rag_tool.search(question)
            
#             if rag_result['success']:
#                 tools_used.append('RAG')
#                 if rag_result['is_relevant']:
#                     if verbose:
#                         print(f"   ✅ Found {len(rag_result['results'])} relevant passages")
                    
#                     # Format RAG context with clear separation
#                     for i, (result, score) in enumerate(zip(rag_result['results'], rag_result['scores']), 1):
#                         # Use newline '\n' instead of literal '\\n' for cleaner Python string output
#                         context_parts.append(
#                             f"[RAG Knowledge Base - Context {i} (Source: {result['source']}, Relevance: {score:.1%})]\n"
#                             f"{result['text']}\n"
#                         )
#                 else:
#                     if verbose:
#                         print("   ℹ️ No relevant RAG results (below threshold)")
#                     context_parts.append("[RAG Knowledge Base]\nNo relevant information found (Score below threshold).\n")
#             else:
#                  context_parts.append(f"[RAG Knowledge Base]\nTool failed to execute: {rag_result.get('error', 'Unknown Error')}\n")
#                  if verbose:
#                      print(f"   ❌ RAG Tool failed: {rag_result.get('error', 'Unknown Error')}")


#         # STEP 3: Call dynamic tools
        
#         def process_tool_result(tool_name: str, data: Dict[str, Any], context_name: str):
#             """Helper function to append successful tool results to context_parts"""
#             summary = data.get('context_summary')
            
#             if data['success'] and summary:
#                 tools_used.append(tool_name)
#                 context_parts.append(f"[{context_name}]\n{summary}\n")
#                 if verbose:
#                     print(f"   ✅ {tool_name} data received.")
#             elif summary:
#                 # Append the summary even if it failed, so the LLM knows the reason
#                 context_parts.append(f"[{context_name}]\nData unavailable. {summary}\n")
#                 if verbose:
#                     print(f"   ❌ {tool_name} failed: {data.get('error', 'Unknown error')}")
#             elif verbose:
#                  print(f"   ❌ {tool_name} failed: No summary provided.")

#         if tool_decisions.get('weather'):
#             if verbose: print("⚙️ Step 3a: Calling Weather Tool...")
#             weather_data = self.weather_tool.get_weather("Hyderabad") # Default city
#             process_tool_result('Weather', weather_data, 'LIVE WEATHER DATA')

#         if tool_decisions.get('market'):
#             if verbose: print("⚙️ Step 3b: Calling Market Price Tool...")
#             # Enhanced simple commodity detection
#             commodities = ['rice', 'wheat', 'cotton', 'tomato', 'maize', 'paddy', 'chili', 'mango']
#             # Find the first matching commodity, otherwise use 'general commodity'
#             commodity = next((c for c in commodities if c in question.lower()), 'general commodity')
#             market_data = self.market_tool.get_price(commodity)
#             process_tool_result('Market', market_data, f'MARKET PRICE DATA - {commodity.upper()}')
        
#         if tool_decisions.get('water'):
#             if verbose: print("⚙️ Step 3c: Calling Water Data Tool...")
#             water_data = self.water_tool.get_water_info("Telangana")
#             process_tool_result('Water', water_data, 'WATER & IRRIGATION DATA')
        
#         if tool_decisions.get('pest'):
#             if verbose: print("⚙️ Step 3d: Calling Pest Advisory Tool...")
#             crops = ['rice', 'wheat', 'cotton', 'tomato', 'mango', 'chili', 'maize', 'paddy']
#             crop = next((c for c in crops if c in question.lower()), 'general crop')
#             pest_data = self.pest_tool.get_pest_info(crop)
#             process_tool_result('Pest', pest_data, f'PEST ADVISORY - {crop.upper()}')
        
#         # STEP 4: Generate answer
#         if verbose:
#             print(f"\n🤖 Step 4: Response Generator creating answer...")
        
#         full_context = "\n".join(context_parts).strip()
        
#         user_prompt = f"""Based on the following data, answer the farmer's question.

# DATA FROM TOOLS:
# {full_context}

# FARMER'S QUESTION: {question}

# ANSWER:""" # The system prompt handles the rest of the instructions
        
#         try:
#             answer = self.response_llm.generate(
#                 self.response_system_prompt, 
#                 user_prompt,
#                 max_tokens=2000,
#                 temperature=0.7
#             )
#         except ConnectionError as e:
#             # Catch the specific error raised if all keys are exhausted
#             answer = f"**Service Error:** {str(e)}"
#             if verbose: print(f"❌ Answer generation failed: {e}")
#         except Exception as e:
#             answer = f"**Internal Error:** Failed to generate response. {str(e)}"
#             if verbose: print(f"❌ Answer generation failed: {e}")

        
#         if verbose:
#             print(f"\n{'='*70}")
#             print("✅ ANSWER GENERATED")
#             print(f"{'='*70}\n")
        
#         # Return the required fields for the FastAPI endpoint
#         return {
#             'question': question,
#             'answer': answer,
#             'tools_used': sorted(list(set(tools_used))), # Ensure unique and sorted
#             'context': full_context,
#         }











# agent.py

import os
import json
import pickle
import numpy as np
import pandas as pd
import faiss
import requests
import time
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer

# ============================================================================
# API KEY ROTATION MANAGER
# ============================================================================

class APIKeyRotator:
    """Manages multiple API keys with automatic rotation and error handling"""
    
    def init(self, api_keys: List[str], cooldown_minutes: int = 5):
        """
        Initialize key rotator
        
        Args:
            api_keys: List of OpenRouter API keys
            cooldown_minutes: Minutes to wait before retrying a failed key
        """
        self.api_keys = api_keys
        self.current_index = 0
        self.cooldown_minutes = cooldown_minutes
        
        # Track failed keys: {key: datetime_of_failure}
        self.failed_keys = {}
        
        # Rate limit error codes (429: Too Many Requests, 402: Payment Required/Quota Exceeded, 503: Service Unavailable)
        self.rate_limit_codes = [429, 402, 503]
        
        print(f"🔑 Key Rotator initialized with {len(api_keys)} keys")
    
    def get_next_key(self) -> Optional[str]:
        """Get next available API key, skipping failed ones"""
        
        # Clean up expired cooldowns
        now = datetime.now()
        expired = [k for k, fail_time in self.failed_keys.items() 
                     if now - fail_time > timedelta(minutes=self.cooldown_minutes)]
        for k in expired:
            del self.failed_keys[k]
            print(f"✅ Key {self._mask_key(k)} cooldown expired, back in rotation")
        
        # Try to find an available key
        attempts = 0
        max_attempts = len(self.api_keys)
        
        while attempts < max_attempts:
            key = self.api_keys[self.current_index]
            
            # Move to next key for next call
            self.current_index = (self.current_index + 1) % len(self.api_keys)
            
            # Check if key is available
            if key not in self.failed_keys:
                return key
            
            attempts += 1
        
        # All keys failed
        print("⚠ All API keys are in cooldown!")
        return None
    
    def mark_key_failed(self, key: str, error_code: int = None):
        """Mark a key as failed (rate limited)"""
        if error_code in self.rate_limit_codes:
            self.failed_keys[key] = datetime.now()
            print(f"❌ Key {self._mask_key(key)} marked as failed (code: {error_code})")
            print(f"   Cooldown: {self.cooldown_minutes} minutes")
    
    def _mask_key(self, key: str) -> str:
        """Mask API key for logging"""
        if len(key) > 10:
            return f"{key[:7]}...{key[-4:]}"
        return "*"
    
    def get_status(self) -> Dict[str, Any]:
        """Get current rotation status"""
        total = len(self.api_keys)
        failed = len(self.failed_keys)
        available = total - failed
        
        # Check if index is valid before masking key
        next_key_masked = self._mask_key(self.api_keys[self.current_index]) if self.api_keys else "N/A"
        
        return {
            'total_keys': total,
            'available_keys': available,
            'failed_keys': failed,
            'current_index': self.current_index,
            'next_key': next_key_masked
        }

# ============================================================================
# ENHANCED LLM INTERFACE WITH KEY ROTATION
# ============================================================================

class OpenRouterLLM:
    """Generic OpenRouter LLM interface with key rotation"""
    
    def init(self, key_rotator: APIKeyRotator, model: str, role: str = "LLM"):
        self.key_rotator = key_rotator
        self.model = model
        self.role = role
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        print(f"🤖 {role} initialized: {model}")
    
    def generate(self, system_prompt: str, user_prompt: str, 
                     max_tokens: int = 1500, temperature: float = 0.7,
                     max_retries: int = 3) -> str:
        """Generate response with automatic key rotation"""
        
        for attempt in range(max_retries):
            # Get next available key
            api_key = self.key_rotator.get_next_key()
            
            if api_key is None:
                # Raise a custom error instead of returning a string, allowing main.py to catch it
                raise ConnectionError(f"❌ {self.role} Error: All API keys exhausted. Please wait {self.key_rotator.cooldown_minutes} minutes.")
            
            try:
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://github.com/agri-agent",
                    "X-Title": "AgriAgent"
                }
                
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                
                # Use a slightly longer timeout for robust requests
                response = requests.post(self.url, headers=headers, json=payload, timeout=90)
                
                # Check for rate limit errors
                if response.status_code in self.key_rotator.rate_limit_codes:
                    self.key_rotator.mark_key_failed(api_key, response.status_code)
                    print(f"⚠ {self.role}: Rate limit hit, trying next key (attempt {attempt+1}/{max_retries})")
                    time.sleep(1) # Small delay before checking next key
                    continue
                
                response.raise_for_status()
                result = response.json()
                return result["choices"][0]["message"]["content"]
            
            except requests.exceptions.RequestException as e:
                error_msg = str(e)
                
                # Check if it's a rate limit error in exception text
                if "429" in error_msg or "quota" in error_msg.lower() or "rate limit" in error_msg.lower():
                    self.key_rotator.mark_key_failed(api_key, 429)
                    print(f"⚠ {self.role}: Rate limit detected in error, trying next key")
                    time.sleep(1) # Small delay before checking next key
                    continue
                
                # Other errors
                if attempt == max_retries - 1:
                    # Raise for non-rate-limit errors on final attempt
                    raise RuntimeError(f"❌ {self.role} Error: Max retries exceeded. Last error: {error_msg}") from e
                
                print(f"⚠ {self.role}: Connection/API error on attempt {attempt+1}, retrying...")
                time.sleep(3) # Longer wait for generic errors
        
        # Should be unreachable, but good practice
        raise RuntimeError(f"❌ {self.role} Error: Max retries exceeded")


class AgentLLM(OpenRouterLLM):
    """Mistral LLM for agent decision-making"""
    
    def init(self, key_rotator: APIKeyRotator, model: str):
        super().init(key_rotator, model, role="Agent LLM (Mistral)")
    
    def decide_tools(self, question: str) -> Dict[str, bool]:
        """Use LLM to decide which tools to call"""
        system_prompt = """You are a tool selection agent. Given a farmer's question, decide which tools to use.

Available tools:
- RAG: Static agriculture knowledge (crop practices, cultivation, soil, etc.)
- Weather: Live weather data (temperature, humidity, rainfall, wind)
- Market: Commodity prices and market rates
- Water: Soil moisture, groundwater, irrigation data
- Pest: Pest and disease management advice

Output ONLY a JSON object with true/false for each tool. Output must be valid JSON and contain ONLY the keys listed.

{
    "rag": true/false,
    "weather": true/false,
    "market": true/false,
    "water": true/false,
    "pest": true/false
}

Rules:
- ALWAYS set "rag": true (we always search RAG first)
- Set other tools to true only if specifically needed
- Be conservative - don't call unnecessary tools"""
        
        user_prompt = f"Question: {question}\n\nWhich tools should be used? Return JSON only."
        
        try:
            response = self.generate(system_prompt, user_prompt, max_tokens=200, temperature=0.3)
            
            # --- Robust JSON Extraction and Parsing ---
            
            # 1. Clean response by removing non-JSON characters/text
            json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
            if json_match:
                json_string = json_match.group().strip()
                
                # 2. Attempt to parse JSON
                decisions = json.loads(json_string)
                
                # 3. Ensure keys are correct and enforce RAG rule
                allowed_keys = ['rag', 'weather', 'market', 'water', 'pest']
                final_decisions = {k: decisions.get(k, False) for k in allowed_keys}
                final_decisions['rag'] = True 
                
                return final_decisions
            else:
                raise ValueError(f"No valid JSON found in LLM response: {response[:100]}...")

        except Exception as e:
            # Catch LLM errors (rate limit, connection, parsing failure)
            print(f"⚠ Agent LLM tool decision error: {e}. Using keyword fallback.")
            # Fallback must be absolutely safe
            return self._fallback_detection(question)
    
    def _fallback_detection(self, question: str) -> Dict[str, bool]:
        """Fallback keyword-based tool detection"""
        q = question.lower()
        return {
            'rag': True, # Always true
            'weather': any(w in q for w in ['weather', 'temperature', 'rain', 'climate', 'humidity', 'wind']),
            'market': any(w in q for w in ['price', 'market', 'cost', 'rate', 'selling', 'commodity']),
            'water': any(w in q for w in ['water', 'irrigation', 'moisture', 'rainfall', 'groundwater']),
            'pest': any(w in q for w in ['pest', 'disease', 'insect', 'fungal', 'virus', 'infection'])
        }


class ResponseGeneratorLLM(OpenRouterLLM):
    """Separate LLM for generating final farmer-facing responses"""
    
    def init(self, key_rotator: APIKeyRotator, model: str):
        super().init(key_rotator, model, role="Response Generator LLM (Gemini/Flash)")


# ============================================================================
# TOOL CLASSES
# ============================================================================

class RAGTool:
    """Searches the FAISS vector database for agriculture knowledge"""
    
    def init(self, index_path: str, metadata_path: str):
        print("📚 Loading RAG Tool...")
        # CRITICAL: Set trust_remote_code=False for security if running locally, 
        # but keep as is if this environment requires it for model loading.
        self.model = SentenceTransformer("all-mpnet-base-v2") 
        self.index = faiss.read_index(index_path)
        
        with open(metadata_path, 'rb') as f:
            data = pickle.load(f)
            self.documents = data['documents']
            self.metadata = data['metadata']
        
        print(f"✅ RAG Tool loaded with {self.index.ntotal} vectors")
    
    def search(self, query: str, k: int = 3, threshold: float = 0.35) -> Dict[str, Any]:
        try:
            query_embedding = self.model.encode([query]).astype('float32')
            
            # --- FAISS Search (Vector is normalized after encoding) ---
            query_embedding = query_embedding / np.linalg.norm(query_embedding)
            distances, indices = self.index.search(query_embedding, k)
            
            # Convert distance (squared Euclidean distance for normalized vectors) to similarity
            # Sim = 1 - (dist^2) / 2 is the exact cosine similarity for L2-normalized vectors
            similarities = 1 - (distances[0] ** 2) / 2
            
            results = []
            scores = []
            
            for idx, score in zip(indices[0], similarities):
                # Check for valid index and threshold
                if score >= threshold and 0 <= idx < len(self.documents):
                    results.append({
                        'text': self.documents[idx],
                        'source': self.metadata[idx]['source'],
                        'type': self.metadata[idx]['type']
                    })
                    scores.append(float(score))
            
            is_relevant = len(results) > 0 and (max(scores) if scores else 0.0) >= threshold
            
            return {
                'success': True,
                'results': results,
                'scores': scores,
                'is_relevant': is_relevant,
                'top_score': max(scores) if scores else 0.0
            }
        
        except Exception as e:
            # Added more context to the error message
            print(f"❌ RAGTool search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'is_relevant': False
            }


class WeatherTool:
    """Fetches live weather data for Telangana cities"""
    
    def init(self, api_key: str):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        
        # Telangana district mapping
        self.district_mapping = {
            # District names (lowercase) -> OpenWeatherMap city names
            'warangal': 'Warangal',
            'khammam': 'Khammam',
            'karimnagar': 'Karimnagar',
            'nizamabad': 'Nizamabad',
            'adilabad': 'Adilabad',
            'nalgonda': 'Nalgonda',
            'mahabubnagar': 'Mahbubnagar',
            'rangareddy': 'Hyderabad',
            'medak': 'Sangareddy',
            'siddipet': 'Siddipet',
            'jagtial': 'Jagtial',
            'jangaon': 'Jangaon',
            'jayashankar': 'Bhupalpalle',
            'jogulamba': 'Jogulamba Gadwal',
            'kamareddy': 'Kamareddy',
            'komaram bheem': 'Asifabad',
            'mancherial': 'Mancherial',
            'medchal': 'Hyderabad',
            'mulugu': 'Mulugu',
            'nagarkurnool': 'Nagarkurnool',
            'narayanpet': 'Narayanpet',
            'peddapalli': 'Peddapalli',
            'rajanna': 'Siricilla',
            'sangareddy': 'Sangareddy',
            'suryapet': 'Suryapet',
            'vikarabad': 'Vikarabad',
            'wanaparthy': 'Wanaparthy',
            'yadadri': 'Yadadri Bhuvanagiri',
            'hyderabad': 'Hyderabad'
        }
        print("🌦 Weather Tool initialized with Telangana district mapping")
    
    def extract_city_from_question(self, question: str) -> str:
        """Extract city name from user's question"""
        question_lower = question.lower()
        
        # Check for district names in the question
        for district, city in self.district_mapping.items():
            if district in question_lower:
                print(f"📍 Detected district '{district}' -> Using city '{city}'")
                return city
        
        # Check for common city names
        common_cities = ['warangal', 'khammam', 'karimnagar', 'nizamabad', 'hyderabad']
        for city in common_cities:
            if city in question_lower:
                print(f"📍 Detected city '{city}'")
                return city.title()
        
        # Default to Hyderabad if no location found
        print("📍 No location detected, defaulting to Hyderabad")
        return "Hyderabad"
    
    def get_weather(self, question: str = None, city: str = None) -> Dict[str, Any]:
        """
        Get weather data. Either use provided city or extract from question.
        """
        # Determine which city to use
        if city:
            target_city = city
        elif question:
            target_city = self.extract_city_from_question(question)
        else:
            target_city = "Hyderabad"  # Fallback default
        
        try:
            params = {
                'q': f"{target_city},IN",
                'appid': self.api_key,
                'units': 'metric'
            }
            
            response = requests.get(self.base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            temp = data['main']['temp']
            humidity = data['main']['humidity']
            description = data['weather'][0]['description']
            wind_speed = data['wind']['speed']
            
            # Enhanced context with detected location
            context_summary = (
                f"Live weather data for {target_city}, Telangana, India: "
                f"Current conditions: '{description}'. "
                f"Temperature: {temp}°C, Humidity: {humidity}%. "
                f"Wind Speed: {wind_speed} m/s."
            )
            
            return {
                'success': True,
                'city': target_city,
                'detected_from_query': question is not None,
                'temperature': temp,
                'humidity': humidity,
                'description': description,
                'wind_speed': wind_speed,
                'context_summary': context_summary
            }
        
        except Exception as e:
            error_msg = f"Weather data for {target_city} is unavailable. Error: {str(e)}"
            return {
                'success': False,
                'error': str(e),
                'city': target_city,
                'context_summary': error_msg
            }

class MarketPriceTool:
    """Fetches commodity prices from local CSV data"""

    # Define the mapping between tool-required columns and your CSV headers
    COLUMN_MAPPING = {
        'Date': 'DDate',
        'Commodity': 'CommName',
        'Market': 'YardName',
        'Variety': 'VarityName',
        'Min_Price': 'Minimum',
        'Max_Price': 'Maximum',
        'Modal_Price': 'Model'  # Added for completeness, if used later
    }
    
    def init(self, csv_path: str):
        print("💰 Loading Market Price Tool...")
        self.prices_df = None
        self.csv_path = csv_path
        
        try:
            if not os.path.exists(csv_path):
                raise FileNotFoundError(f"CSV file not found at path: {csv_path}")
                
            self.prices_df = pd.read_csv(csv_path)
            
            # --- CRITICAL FIX: Rename columns here ---
            # Create a reverse mapping for Pandas: {CSV_Header: Tool_Required_Name}
            reverse_mapping = {v: k for k, v in self.COLUMN_MAPPING.items()}
            
            # Filter the mapping to only rename columns that exist in the loaded CSV
            columns_to_rename = {
                csv_col: tool_col 
                for csv_col, tool_col in reverse_mapping.items() 
                if csv_col in self.prices_df.columns
            }
            
            # Perform the renaming in place
            self.prices_df.rename(columns=columns_to_rename, inplace=True)
            # --- END CRITICAL FIX ---

            # Check for the newly renamed required columns
            required_cols = ['Commodity', 'Market', 'Variety', 'Min_Price', 'Max_Price', 'Date']
            
            if not all(col in self.prices_df.columns for col in required_cols):
                print(f"⚠ Warning: Market Price CSV missing some required columns AFTER RENAME: {required_cols}")
            
            print(f"✅ Loaded {len(self.prices_df)} price records")
        except Exception as e:
            print(f"⚠ Error loading market prices: {e}")
            self.prices_df = None
    
    # get_price method 
    def get_price(self, commodity: str, market: Optional[str] = None) -> Dict[str, Any]:
        if self.prices_df is None:
            return {
                'success': False,
                'error': 'Market price data not available. Check file path.',
                'context_summary': 'Market price data is currently unavailable.'
            }
        
        try:
            commodity_lower = commodity.lower()
            
            # Filter rows where the commodity name (or related keyword) appears
            matches = self.prices_df[
                self.prices_df.apply(
                    # This correctly uses the renamed 'Commodity' column
                    lambda row: commodity_lower in str(row).lower(), 
                    axis=1
                )
            ]
            
            if len(matches) == 0:
                return {
                    'success': False,
                    'error': f'No price data found for {commodity}',
                    'commodity': commodity,
                    'context_summary': f'No recent market price data found for {commodity}.'
                }
            
            price_records = matches.to_dict('records')
            top_records = price_records[:5]
            
            # --- Context Summary uses the correctly renamed columns ---
            summary_lines = [f"Found {len(price_records)} market price records for {commodity.upper()}:"]
            for record in top_records:
                try:
                    line = (
                        f"• {record.get('Market', 'N/A')} ({record.get('Date', 'N/A')}): "
                        f"Variety: {record.get('Variety', 'N/A')}. "
                        f"Price Range: ₹{record.get('Min_Price', 'N/A')} - ₹{record.get('Max_Price', 'N/A')}."
                    )
                    summary_lines.append(line)
                except Exception:
                    summary_lines.append(f"• Price data record: {record}")
            
            context_summary = "\n".join(summary_lines)
            
            return {
                'success': True,
                'commodity': commodity,
                'records_found': len(price_records),
                'prices': top_records, 
                'context_summary': context_summary
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'context_summary': f'Error fetching market price data: {str(e)}'
            }


class WaterDataTool:
    """Provides soil moisture, rainfall, and groundwater information (Mock Data)"""
    
    def init(self):
        print("💧 Water Data Tool initialized (using mock data)")
        self.data = {
            'telangana': {
                'avg_rainfall_mm': 850,
                'groundwater_level': 'Moderate (requires monitoring)',
                'soil_moisture': 'Medium (adequate for Kharif sowing)',
                'irrigation_advice': 'Use drip or micro-sprinkler irrigation systems for water conservation'
            }
        }
    
    def get_water_info(self, region: str = "Telangana") -> Dict[str, Any]:
        try:
            region_data = self.data.get(region.lower(), self.data['telangana'])
            
            # --- Context Summary for LLM (Human Readable) ---
            context_summary = (
                f"Water & Irrigation Data for {region}: "
                f"Average annual rainfall: {region_data['avg_rainfall_mm']}mm. "
                f"Groundwater level status: {region_data['groundwater_level']}. "
                f"Current soil moisture: {region_data['soil_moisture']}. "
                f"Recommendation: {region_data['irrigation_advice']}."
            )
            
            return {
                'success': True,
                'region': region,
                'avg_rainfall_mm': region_data['avg_rainfall_mm'],
                'context_summary': context_summary
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'context_summary': f'Error fetching water data: {str(e)}'
            }


class PestAdvisoryTool:
    """Provides pest and disease management advice (Mock Data)"""
    
    def init(self):
        print("🐛 Pest Advisory Tool initialized (using mock data)")
        self.common_pests = {
            'tomato': ['fruit borer', 'leaf curl virus', 'whitefly', 'early blight'],
            'rice': ['stem borer', 'blast disease', 'brown planthopper (BPH)', 'sheath blight'],
            'cotton': ['bollworm (pink/American)', 'whitefly', 'aphids', 'jassids'],
            'wheat': ['rust', 'aphids', 'termites', 'loose smut']
        }
    
    def get_pest_info(self, crop: str) -> Dict[str, Any]:
        try:
            crop_lower = crop.lower()
            pests = self.common_pests.get(crop_lower, [])
            
            if pests:
                advice = (
                    f"Common pests for {crop}: {', '.join(pests)}. "
                    f"Use Integrated Pest Management (IPM) practices, including regular field scouting, "
                    f"using resistant varieties, and only applying targeted pesticides when necessary. "
                    f"Consult the local agricultural extension office for specific treatment protocols."
                )
            else:
                 advice = (
                    f"No specific common pest list found for '{crop}'. "
                    f"General advice: Monitor your crop for signs of pests or diseases, "
                    f"maintain good field hygiene, and practice crop rotation."
                )
            
            return {
                'success': True,
                'crop': crop,
                'common_pests': pests,
                'advice': advice,
                'context_summary': advice
            }
        
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'context_summary': f'Error fetching pest data: {str(e)}'
            }


# ============================================================================
# MAIN AGRI-AGENT WITH KEY ROTATION
# ============================================================================

class AgriAgent:
    """Agricultural Agent with multi-key rotation support"""
    
    def init(
        self,
        openrouter_keys: List[str],
        openweather_key: str,
        faiss_index_path: str,
        metadata_path: str,
        market_prices_path: str,
        response_llm_model: str,
        agent_llm_model: str,
        key_cooldown_minutes: int
    ):
        print("\n" + "="*70)
        print("🌾 INITIALIZING AGRIAGENT WITH KEY ROTATION")
        print("="*70 + "\n")
        
        # Initialize key rotator
        self.key_rotator = APIKeyRotator(openrouter_keys, key_cooldown_minutes)
        
        # Initialize tools
        self.rag_tool = RAGTool(faiss_index_path, metadata_path)
        self.weather_tool = WeatherTool(openweather_key)
        self.market_tool = MarketPriceTool(market_prices_path)
        self.water_tool = WaterDataTool()
        self.pest_tool = PestAdvisoryTool()
        
        # Initialize dual LLMs with key rotator
        print("\n📋 Dual LLM Architecture with Key Rotation:")
        self.agent_llm = AgentLLM(self.key_rotator, agent_llm_model)
        self.response_llm = ResponseGeneratorLLM(self.key_rotator, response_llm_model)
        
        # System prompt for the final response LLM
        self.response_system_prompt = """You are AgriAgent, an expert agricultural advisor for Indian farmers in Telangana.

CRITICAL RULES:
1. Base your answer STRICTLY on the provided context data from RAG and other tools.
2. NEVER hallucinate or invent numbers—all data must come from the context.
3. If data is missing or a tool failed, clearly state the missing information (e.g., "Market price data is unavailable").
4. Keep responses clear, practical, and agriculture-focused.
5. Prioritize Indian farming practices and Telangana conditions.
6. Format the response to be easily readable, using paragraphs and bullet points where appropriate.

RESPONSE STRUCTURE:
Start with a direct, comprehensive answer. Follow with a detailed breakdown.
"""
        
        print("\n" + "="*70)
        print("✅ AGRIAGENT READY!")
        print("="*70 + "\n")
    
    def query(self, question: str, verbose: bool = False) -> Dict[str, Any]:
        """Process farmer's question through the agent pipeline"""
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"❓ QUESTION: {question}")
            print(f"{'='*70}\n")
            
            status = self.key_rotator.get_status()
            print(f"🔑 Key Status: {status['available_keys']}/{status['total_keys']} available")
        
        tools_used = []
        context_parts = []
        
        # STEP 1: Agent LLM decides tools
        if verbose:
            print("\n🧠 Step 1: Agent LLM deciding tools...")
        
        tool_decisions = self.agent_llm.decide_tools(question)
        
        if verbose:
            print(f"   Tools selected: {[k for k, v in tool_decisions.items() if v]}")
        
        # STEP 2: Call RAG (Always run if successful)
        rag_result = {'success': False, 'is_relevant': False}
        if tool_decisions.get('rag', True):
            if verbose:
                print("\n⚙ Step 2: Calling RAG Tool...")
            
            rag_result = self.rag_tool.search(question)
            
            if rag_result['success']:
                tools_used.append('RAG')
                if rag_result['is_relevant']:
                    if verbose:
                        print(f"   ✅ Found {len(rag_result['results'])} relevant passages")
                    
                    # Format RAG context with clear separation
                    for i, (result, score) in enumerate(zip(rag_result['results'], rag_result['scores']), 1):
                        # Use newline '\n' instead of literal '\\n' for cleaner Python string output
                        context_parts.append(
                            f"[RAG Knowledge Base - Context {i} (Source: {result['source']}, Relevance: {score:.1%})]\n"
                            f"{result['text']}\n"
                        )
                else:
                    if verbose:
                        print("   ℹ No relevant RAG results (below threshold)")
                    context_parts.append("[RAG Knowledge Base]\nNo relevant information found (Score below threshold).\n")
            else:
                 context_parts.append(f"[RAG Knowledge Base]\nTool failed to execute: {rag_result.get('error', 'Unknown Error')}\n")
                 if verbose:
                     print(f"   ❌ RAG Tool failed: {rag_result.get('error', 'Unknown Error')}")


        # STEP 3: Call dynamic tools
        
        def process_tool_result(tool_name: str, data: Dict[str, Any], context_name: str):
            """Helper function to append successful tool results to context_parts"""
            summary = data.get('context_summary')
            
            if data['success'] and summary:
                tools_used.append(tool_name)
                context_parts.append(f"[{context_name}]\n{summary}\n")
                if verbose:
                    print(f"   ✅ {tool_name} data received.")
            elif summary:
                # Append the summary even if it failed, so the LLM knows the reason
                context_parts.append(f"[{context_name}]\nData unavailable. {summary}\n")
                if verbose:
                    print(f"   ❌ {tool_name} failed: {data.get('error', 'Unknown error')}")
            elif verbose:
                 print(f"   ❌ {tool_name} failed: No summary provided.")

        if tool_decisions.get('weather'):
            if verbose: print("⚙ Step 3a: Calling Weather Tool...")
            weather_data = self.weather_tool.get_weather(question=question) # Default city
            process_tool_result('Weather', weather_data, 'LIVE WEATHER DATA')

        if tool_decisions.get('market'):
            if verbose: print("⚙ Step 3b: Calling Market Price Tool...")
            # Enhanced simple commodity detection
            commodities = ['rice', 'wheat', 'cotton', 'tomato', 'maize', 'paddy', 'chili', 'mango']
            # Find the first matching commodity, otherwise use 'general commodity'
            commodity = next((c for c in commodities if c in question.lower()), 'general commodity')
            market_data = self.market_tool.get_price(commodity)
            process_tool_result('Market', market_data, f'MARKET PRICE DATA - {commodity.upper()}')
        
        if tool_decisions.get('water'):
            if verbose: print("⚙ Step 3c: Calling Water Data Tool...")
            water_data = self.water_tool.get_water_info("Telangana")
            process_tool_result('Water', water_data, 'WATER & IRRIGATION DATA')
        
        if tool_decisions.get('pest'):
            if verbose: print("⚙ Step 3d: Calling Pest Advisory Tool...")
            crops = ['rice', 'wheat', 'cotton', 'tomato', 'mango', 'chili', 'maize', 'paddy']
            crop = next((c for c in crops if c in question.lower()), 'general crop')
            pest_data = self.pest_tool.get_pest_info(crop)
            process_tool_result('Pest', pest_data, f'PEST ADVISORY - {crop.upper()}')
        
        # STEP 4: Generate answer
        if verbose:
            print(f"\n🤖 Step 4: Response Generator creating answer...")
        
        full_context = "\n".join(context_parts).strip()
        
        user_prompt = f"""Based on the following data, answer the farmer's question.

DATA FROM TOOLS:
{full_context}

FARMER'S QUESTION: {question}

ANSWER:""" # The system prompt handles the rest of the instructions
        
        try:
            answer = self.response_llm.generate(
                self.response_system_prompt, 
                user_prompt,
                max_tokens=2000,
                temperature=0.7
            )
        except ConnectionError as e:
            # Catch the specific error raised if all keys are exhausted
            answer = f"Service Error: {str(e)}"
            if verbose: print(f"❌ Answer generation failed: {e}")
        except Exception as e:
            answer = f"Internal Error: Failed to generate response. {str(e)}"
            if verbose: print(f"❌ Answer generation failed: {e}")

        
        if verbose:
            print(f"\n{'='*70}")
            print("✅ ANSWER GENERATED")
            print(f"{'='*70}\n")
        
        # Return the required fields for the FastAPI endpoint
        return {
            'question': question,
            'answer': answer,
            'tools_used': sorted(list(set(tools_used))), # Ensure unique and sorted
            'context': full_context,
        }