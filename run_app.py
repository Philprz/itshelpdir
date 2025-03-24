# -*- coding: utf-8 -*- 
import os 
import logging 
from flask import Flask, render_template, request, jsonify 
from dotenv import load_dotenv 
 
logging.basicConfig(level=logging.DEBUG) 
load_dotenv() 
 
app = Flask(__name__) 
 
@app.route('/') 
def index(): 
    return render_template('index.html') 
 
@app.route('/api/message', methods=['POST']) 
def process_message(): 
    data = request.json 
    return jsonify({"message": "Ceci est une version de test simplifiee. L'application complete necessite Socket.IO.", "blocks": []}) 
 
if __name__ == '__main__': 
    app.run(debug=True, host='0.0.0.0', port=int(os.getenv('PORT', 5000))) 
