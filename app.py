# Python Flask Web
import os
from flask import Flask, render_template, request, url_for
from werkzeug.utils import secure_filename

import google.generativeai as genai
from google.generativeai.types import (
    HarmBlockThreshold,
    HarmCategory,
    GenerationConfig,
)
import configparser
import time
import configparser
import json
import time
import random
import re

config = configparser.ConfigParser()
config.read('config.ini')
api_keys = config.get('Google', 'GEMINI_API_KEY').replace('\n', '').split(',')
genai.configure(api_key=random.choice(api_keys))
    
def prompt_to_json(prompt, videofile):
    try:
        model = genai.GenerativeModel(
            "gemini-1.5-flash",
            safety_settings={
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            },
            generation_config={
                "temperature": 0,
                "top_p": 0.01,
                "top_k": 1,
                "max_output_tokens": 8192,  # 設定輸出的最大字元數
                "response_mime_type": "application/json",
            },
            system_instruction="中文的部分請使用繁體中文，日文的部分請使用日文。",
        )

        result = ""
        total_tokens = 0
        history = []

        # Start chat session outside of the loop
        chat_session = model.start_chat(history=history)
        first_response = chat_session.send_message([prompt, videofile])
        
        if not first_response._result.candidates:
            raise ValueError("No candidates in response.")
        
        response_text = first_response._result.candidates[0].content.parts[0].text
        result += response_text
        token_count = first_response._result.usage_metadata.candidates_token_count
        total_tokens += token_count
        history.append({"role": "user", "parts": [prompt]})
        history.append({"role": "model", "parts": [response_text]})

        print(f"Current result: {result[:100]}...{result[-100:]}")
        print(f"Current token count: {total_tokens}")

        while token_count > 8000:
            chat_session = model.start_chat(history=history)
            message = f"""請繼續'{result[-50]}'上次未完成的 JSON 輸出，對話請不要輸出「」，
            不要從`dialogs`輸出，只輸出尚未出現的字元，並且不能缺失字元，請思考影片長度為多少，
            並剛好輸出至影片長度，到達影片長度後請勿繼續輸出，格式如下：
            {{["00:00","00:05","日文對話","中文對話"],...}}
            """
            # message = '請完全接續上次輸出的內容，例如:上次輸出的結尾為"time": "11:42", "jp": "封じ込めて，這次的開頭必須為やった。", "zh": "把她關起來了"}'
            response = chat_session.send_message([message, videofile])
            if not response._result.candidates:
                 raise ValueError("No candidates in response.")
            response_text = response._result.candidates[0].content.parts[0].text
            if result[-10:] in response_text:
                response_text = response_text.replace(response_text[:response_text.index(result[-10:])+10], "")
            else:
                return prompt_to_json(prompt, videofile)
            result += response_text
            token_count = response._result.usage_metadata.candidates_token_count
            total_tokens += token_count

            history.append({"role": "user", "parts": [message]})
            history.append({"role": "model", "parts": [response_text]})

            print(f"Current result: {response_text[:100]}...{response_text[-100:]}")
            print(f"Current token count: {token_count}")

        

    except json.JSONDecodeError as e:
         print(f"JSON Decode Error: {e}")
         raise
    except Exception as e:
        print(f"An error occurred: {e}. Waiting 10 seconds...")
        time.sleep(10)
        return prompt_to_json(prompt, videofile)
    try:
        result = json.loads(result)
        return result
    except json.JSONDecodeError as e:
        print(f"JSON Decode Error: {e}")
        return prompt_to_json(prompt, videofile)


UPLOAD_FOLDER = "static/data"
ALLOWED_EXTENSIONS = set(["mp4","mov","avi","webm","wmv","3gp","flv","mpg","mpeg"])

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/submit", methods=["POST"])
def submit():
    print("Submit!")
    if request.method == "POST":
        if "file1" not in request.files:
            print("No file part")
            return render_template("index.html")
        file = request.files["file1"]
        if file.filename == "":
            print("No selected file")
            return render_template("index.html")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            print(filename)
            global video_file_gemini
            video_file_gemini = upload_to_gemini(filename)
            result = "檔案已上傳成功! 並提供給Gemini處理完畢!"
            # prompt="""
            # 請幫我把這部影片的時間點與對話全部列出來，必須有日文與中文，並且幫我把這些對話轉換成json格式，格式如下：
            # {'dialogs': [{'time': "00:00", 'jp': "日文對話", 'zh': "中文對話"}, {'time': "00:01", 'jp': "日文對話", 'zh': "中文對話"},...]}
            # """
            prompt="""
            請幫我把這部影片的時間點(開始與結束)與對話全部列出來，對話請不要輸出「」，
            必須有日文與中文，並且幫我把這些對話轉換成json格式，格式如下：
            {'dialogs': [["00:00","00:05","日文對話","中文對話"],...]}
            """
            
            response = prompt_to_json(prompt,video_file_gemini)
            
        return render_template("index.html",prediction=result,filename=filename,response=response)
    else:
        return render_template("index.html", prediction="Method not allowed")


def upload_to_gemini(filename):
    print(f"Uploading file...")
    video_file = genai.upload_file(path=f"static/data/{filename}")
    print(f"Completed upload: {video_file}")
    while video_file.state.name == "PROCESSING":
        print("Waiting for video to be processed.")
        time.sleep(1)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise ValueError(video_file.state.name)
    print(f"Video processing complete: " + video_file.uri)
    return video_file

if __name__ == "__main__":
    # app.run(port=5001, debug=True)
    app.run(host="0.0.0.0")