import requests
from flask import request, g, Flask, jsonify
from sqlite3 import dbapi2 as sqlite3
import os
import random

# local files
# needs to include a key 'verification_token' with Slack's verification token
from config import config 
# customize actions here
from actions import actions
 
app = Flask(__name__)

DATABASE = './slack_actions.db'

### DATABASE functions
def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

def change_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    
def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv
    
def close_db():
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

### OTHER FUNCTIONS
def send_post_request(endpoint, json):
    response = requests.post(endpoint, json=json)

### API
@app.route('/list', methods=['POST'])
def list():
    if not request.form['token'] == config['verification_token']:
        return 'Sorry, incorrect token'
    
    response_message = 'List of available commands:'
    for key in actions:
        response_message += '\n/{}'.format(key)
    
    response_dict = {'response_type': 'ephemeral', 'text': response_message}
    
    return jsonify(response_dict)
    
@app.route('/stats', methods=['POST'])
def stats():
    if not request.form['token'] == config['verification_token']:
        return 'Sorry, incorrect token'
    
    user = request.form['user_id']
    
    sending_hists = query_db('SELECT action, SUM(num_action) as total FROM actions WHERE user1 = ? GROUP BY action', [user])
    receiving_hists = query_db('SELECT action, SUM(num_action) as total FROM actions WHERE user2 = ? GROUP BY action', [user])
    
    response_message = 'Your stats:'
    for sending_hist in sending_hists:
        action_type = sending_hist['action']
        action = actions[action_type]
        num_total = sending_hist['total']
        
        action_send = action['action_send'].format('You', num_total)
    
        response_message += '\n{}'.format(action_send)

    for receiving_hist in receiving_hists:
            action_type = receiving_hist['action']
            action = actions[action_type]
            num_total = receiving_hist['total']
            
            action_send = action['action_received'].format('You', num_total)
        
            response_message += '\n{}'.format(action_send)
    
    response_dict = {'response_type': 'ephemeral', 'text': response_message}
    
    return jsonify(response_dict)
    
@app.route('/action', methods=['POST'])
def action():
    if not request.form['token'] == config['verification_token']:
        return 'Sorry, incorrect token'

    action_type_raw = request.form['command']
    action_type_length = len(action_type_raw)
    action_type = action_type_raw[1:action_type_length]

    if action_type not in actions:
        return 'Sorry, invalid command'
    
    action = actions[action_type]
    
    user1 = request.form['user_id']
    
    action_appendix = request.form['text']
    user_name_start = 1 + action_appendix.find("@")
    user_name_end = action_appendix.find("|") + 1
    length = user_name_end - user_name_start + 1
    user2 = action_appendix[user_name_start:length]
    
    if user1 == user2:
        return 'Sorry, can\'t perform action on yourself'
    
    action_hist = query_db('SELECT * FROM actions WHERE action = ? and user1 = ? AND user2 = ?', [action['action'], user1, user2], one=True) 
    if action_hist is None:
        change_db('INSERT INTO actions(action, user1, user2, num_action) VALUES (?, ?, ?, ?)', [action['action'], user1, user2, 1]) 
    else:
        action_id = action_hist['id']
        action_times = action_hist['num_action'] + 1
        change_db('UPDATE actions SET num_action = ? WHERE id = ?', [action_times, action_id])
    
    slack_user1 = '<@{}>'.format(user1)
    slack_user2 = '<@{}>'.format(user2)
    
    return_message_list = action['action_message']
    return_message_template = random.choice(return_message_list)
    return_message = return_message_template.format(slack_user1, slack_user2)
    
    # do not return immediately, so that the command isn't visible to the sender
    response_url = request.form['response_url']
    response_dict = {'response_type': 'in_channel', 'text': return_message}
    send_post_request(response_url, response_dict)
    
    response_dict = {'response_type': 'ephemeral', 'text': 'You did it. Sadly Slack seems to require a message but at least it\'s only visible to you.'}
    return jsonify(response_dict)
        
@app.teardown_appcontext
def close_connection(exception):
    close_db()    
    
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 63335))
    #init_db()    
    app.run(host='0.0.0.0', port=port, debug=True)
    