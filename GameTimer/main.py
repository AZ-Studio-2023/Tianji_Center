from flask import Flask, request, jsonify
import requests
import sqlite3
import time
from datetime import datetime, timedelta
import threading
import json

app = Flask(__name__)

def init_db():
    conn = sqlite3.connect('player_stats.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS player_stats
                 (player TEXT PRIMARY KEY, minutes INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def update_player_stats():
    while True:
        try:
            response = requests.get('http://127.0.0.1:8888/info')
            if response.status_code == 200:
                data = response.json()
                players = [p['player'] for p in data[0]] 
                
                conn = sqlite3.connect('player_stats.db')
                c = conn.cursor()
                
                for player in players:
                    c.execute('INSERT OR REPLACE INTO player_stats (player, minutes) VALUES (?, COALESCE((SELECT minutes FROM player_stats WHERE player = ?) + 1, 1))', (player, player))
                
                conn.commit()
                conn.close()
        except Exception as e:
            print(f"Error updating stats: {e}")
        
        time.sleep(60)  # 等待1分钟



@app.route('/query')
def query_stats():
    query_type = request.args.get('type', 'all')
    time_type = request.args.get('time', 'day')
    player = request.args.get('player', '')
    
    conn = sqlite3.connect('player_stats.db')
    c = conn.cursor()
    
    if query_type == 'player':
        if not player:
            return jsonify({"error": "需要提供player参数"}), 400
        
        c.execute('SELECT minutes FROM player_stats WHERE player = ?', (player,))
        result = c.fetchone()
        if result:
            return jsonify({
                "player": player,
                "time": result[0]
            })
        return jsonify({"error": "未找到该玩家"}), 404
    
    # 处理时间范围
    now = datetime.now()
    if time_type == 'day':
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif time_type == 'week':
        start_time = now - timedelta(days=now.weekday())
    elif time_type == 'month':
        start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:  # all
        start_time = datetime.min
    
    # 获取所有玩家的统计数据
    c.execute('SELECT player, minutes FROM player_stats ORDER BY minutes DESC')
    results = c.fetchall()
    
    conn.close()
    
    # 格式化结果
    formatted_results = []
    for player, minutes in results:
        formatted_results.append({
            "player": player,
            "time": minutes
        })
    
    return jsonify(formatted_results)

if __name__ == '__main__':
    init_db()
    # 启动后台线程进行数据更新
    update_thread = threading.Thread(target=update_player_stats, daemon=True)
    update_thread.start()
    
    app.run(host='0.0.0.0', port=1000)
