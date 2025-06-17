from flask import Flask, render_template, request, jsonify, send_file
import requests
from bs4 import BeautifulSoup
import pandas as pd
import io
import os
from urllib.parse import quote_plus, urlparse
import time
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

app = Flask(__name__)

# Google Custom Search APIの設定
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', 'AIza*********')  # .envファイルから読み込み、なければデフォルト値
GOOGLE_CX = os.getenv('GOOGLE_CX', 'd31**********')  # .envファイルから読み込み、なければデフォルト値

def search_google(query, num_results=10):
    """Google Custom Search APIを使用して検索を実行"""
    base_url = "https://www.googleapis.com/customsearch/v1"
    
    all_results = []
    
    # Google Custom Search APIは1回のリクエストで最大10件まで
    for start_index in range(1, num_results + 1, 10):
        params = {
            'key': GOOGLE_API_KEY,
            'cx': GOOGLE_CX,
            'q': query,
            'start': start_index,
            'num': min(10, num_results - len(all_results))
        }
        
        try:
            response = requests.get(base_url, params=params)
            data = response.json()
            
            if 'error' in data:
                print(f"API エラー: {data['error']['message']}")
                return []
            
            if 'items' in data:
                for item in data['items']:
                    # スポンサーリンクや広告を除外（タイトルやスニペットで判断）
                    if not any(word in item.get('title', '').lower() + item.get('snippet', '').lower() 
                             for word in ['広告', 'ad', 'sponsored', 'スポンサー']):
                        all_results.append(item['link'])
                        if len(all_results) >= num_results:
                            break
            
            if len(all_results) >= num_results:
                break
                
        except Exception as e:
            print(f"検索エラー: {e}")
            return []
    
    return all_results[:num_results]

def extract_text_from_url(url):
    """URLからテキストを抽出"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # スクリプトとスタイルを除去
        for script in soup(["script", "style"]):
            script.decompose()
        
        # テキストを抽出
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    
    except Exception as e:
        print(f"URL {url} からのテキスト抽出エラー: {e}")
        return ""

def check_keywords_in_text(text, keywords):
    """テキスト内にキーワードが含まれているかチェック"""
    results = {}
    for keyword in keywords:
        if keyword and keyword in text:
            results[keyword] = "○"
        else:
            results[keyword] = "×"
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.json
    search_keyword = data.get('search_keyword', '')
    contain_keywords = data.get('contain_keywords', '').strip().split('\n')
    contain_keywords = [kw.strip() for kw in contain_keywords if kw.strip()]
    
    if not search_keyword or not contain_keywords:
        return jsonify({'error': 'キーワードを入力してください'})
    
    # Google検索実行
    urls = search_google(search_keyword)
    
    if not urls:
        return jsonify({'error': '検索結果が取得できませんでした'})
    
    # 各URLからテキストを抽出し、キーワードをチェック
    url_results = {}
    keyword_counts = {kw: 0 for kw in contain_keywords}
    
    for i, url in enumerate(urls):
        time.sleep(1)  # サーバーへの負荷を軽減
        text = extract_text_from_url(url)
        domain = urlparse(url).netloc
        url_results[domain] = {}
        
        for keyword in contain_keywords:
            if keyword and keyword in text:
                url_results[domain][keyword] = "○"
                keyword_counts[keyword] += 1
            else:
                url_results[domain][keyword] = "×"
    
    # キーワードを含有数で降順ソート
    sorted_keywords = sorted(contain_keywords, key=lambda k: keyword_counts[k], reverse=True)
    
    return jsonify({
        'url_results': url_results,
        'keywords': sorted_keywords,
        'keyword_counts': keyword_counts,
        'urls': list(url_results.keys())
    })

@app.route('/download_csv', methods=['POST'])
def download_csv():
    data = request.json
    url_results = data.get('url_results', {})
    keywords = data.get('keywords', [])
    keyword_counts = data.get('keyword_counts', {})
    
    if not url_results:
        return "データがありません", 400
    
    # DataFrameを作成（縦軸：キーワード、横軸：URL）
    df_data = []
    for keyword in keywords:
        row = {'キーワード': keyword}
        for url in url_results:
            row[url] = url_results[url].get(keyword, '×')
        row['含有サイト数'] = keyword_counts.get(keyword, 0)
        df_data.append(row)
    
    df = pd.DataFrame(df_data)
    
    # CSVファイルとして出力
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='keyword_analysis_results.csv'
    )

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))