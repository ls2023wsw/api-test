from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_cors import CORS
import requests
import threading
import time
import uuid
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# 存储测试信息
test_sessions = {}
excel_file = 'test_results.xlsx'

# 初始化 Excel 文件
def init_excel():
    if not os.path.exists(excel_file):
        df = pd.DataFrame(columns=['URL', 'API Key', 'Models', 'Results'])
        df.to_excel(excel_file, index=False)

# 保存到 Excel 文件
def save_to_excel(url, key, models, results):
    if os.path.exists(excel_file):
        df = pd.read_excel(excel_file)
    else:
        df = pd.DataFrame(columns=['URL', 'API Key', 'Models', 'Results'])
    
    new_row = pd.DataFrame({'URL': [url], 'API Key': [key], 'Models': [models], 'Results': [results]})
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_excel(excel_file, index=False)

# 分类存储正常和不正常的模型
def test_model(model, url, key, session_id):
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": "你好"}]
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response_json = response.json()
        
        if response.status_code == 200 and "choices" in response_json and len(response_json["choices"]) > 0:
            reply = response_json["choices"][0]["message"]["content"]
            if reply.strip():  # 检查回复是否为空
                test_sessions[session_id]['normal_models'].append(model)
            else:
                test_sessions[session_id]['abnormal_models'].append(model)  # 回复为空也算异常
        else:
            test_sessions[session_id]['abnormal_models'].append(model)
    except Exception as e:
        test_sessions[session_id]['abnormal_models'].append(model)
    
    test_sessions[session_id]['progress'] += 1

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_test', methods=['POST'])
def start_test():
    url = request.form['url']
    key = request.form['key']
    models = [model.strip() for model in request.form['models'].split(',')]
    
    # 服务器端验证
    if not url or '/v1/chat/completions' not in url:
        flash('URL 必须包含 "/v1/chat/completions"。')
        return redirect(url_for('index'))

    if not key:
        flash('API Key 是必填项。')
        return redirect(url_for('index'))

    if not models or models == ['']:
        flash('模型列表是必填项。')
        return redirect(url_for('index'))

    # 生成唯一的会话 ID
    session_id = str(uuid.uuid4())
    
    # 存储测试信息
    test_sessions[session_id] = {
        'url': url,
        'key': key,
        'models': models,
        'normal_models': [],
        'abnormal_models': [],
        'progress': 0
    }

    # 保存到 Excel 文件
    save_to_excel(url, key, ', '.join(models), 'In Progress')

    # 启动测试线程
    thread = threading.Thread(target=run_tests, args=(session_id,))
    thread.start()

    return redirect(url_for('results', session_id=session_id))


def run_tests(session_id):
    url = test_sessions[session_id]['url']
    key = test_sessions[session_id]['key']
    models = test_sessions[session_id]['models']

    for model in models:
        test_model(model, url, key, session_id)
        time.sleep(0.5)  # 每秒最多发送两个请求

    # 测试完成后更新结果
    results = f"Normal: {len(test_sessions[session_id]['normal_models'])}, Abnormal: {len(test_sessions[session_id]['abnormal_models'])}"
    save_to_excel(url, key, ', '.join(models), results)

@app.route('/results')
def results():
    session_id = request.args.get('session_id')
    if session_id in test_sessions:
        return render_template('results.html', session_id=session_id, total=len(test_sessions[session_id]['models']))
    return "Session not found", 404

@app.route('/start_results_test/<session_id>', methods=['POST'])
def start_results_test(session_id):
    if session_id in test_sessions:
        # 重置进度和模型列表
        test_sessions[session_id]['normal_models'] = []
        test_sessions[session_id]['abnormal_models'] = []
        test_sessions[session_id]['progress'] = 0
        
        # 启动测试线程
        thread = threading.Thread(target=run_tests, args=(session_id,))
        thread.start()
        
        return redirect(url_for('results', session_id=session_id))
    return "Session not found", 404

@app.route('/progress/<session_id>')
def get_progress(session_id):
    if session_id in test_sessions:
        return jsonify({
            "progress": test_sessions[session_id]['progress'],
            "total": len(test_sessions[session_id]['models']),
            "normal": test_sessions[session_id]['normal_models'],
            "abnormal": test_sessions[session_id]['abnormal_models']
        })
    return jsonify({"error": "Session not found"}), 404

if __name__ == '__main__':
    init_excel()  # 初始化 Excel 文件
    app.run(debug=True, port=2984)
    CORS(app)
