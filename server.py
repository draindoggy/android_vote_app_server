from flask import Flask, request, jsonify
from web3 import Web3
import json
import re

app = Flask(__name__)

infura_url = "https://sepolia.infura.io/v3/a2a128abd3f841b88748ebcd27e9fdb3"
web3 = Web3(Web3.HTTPProvider(infura_url))

contract_address = Web3.to_checksum_address("0xd05cecaaC26b315051B9C2FaBAf79b60De933f72")
with open("diplom.abi", "r") as abi_file:
    contract_abi = json.load(abi_file)

contract = web3.eth.contract(address=contract_address, abi=contract_abi)

cache = {
    "polls": None,
    "results": {},  
    "voted_users": {}  
}

def is_valid_private_key(private_key):
    private_key = private_key.strip().lower()
    if private_key.startswith('0x'):
        private_key = private_key[2:]
    pattern = re.compile(r'^[0-9a-f]{64}$')
    return bool(pattern.match(private_key))

@app.route('/create_poll', methods=['POST'])
def create_poll():
    data = request.get_json()
    poll_name = data.get('poll_name')
    options = data.get('options')
    account = data.get('account')
    private_key = data.get('private_key')

    if not poll_name or not options or not isinstance(options, list):
        return jsonify({"success": False, "error": "Название опроса или варианты ответа не могут быть пустыми."}), 400

    if not web3.is_address(account):
        return jsonify({"success": False, "error": "Некорректный адрес кошелька."}), 400

    if not is_valid_private_key(private_key):
        return jsonify({"success": False, "error": "Некорректный приватный ключ."}), 400

    nonce = web3.eth.get_transaction_count(account)

    try:
        transaction = contract.functions.createPoll(poll_name, options).build_transaction({
            'chainId': 11155111,
            'gas': 2000000,
            'gasPrice': web3.to_wei('25', 'gwei'),
            'nonce': nonce,
        })
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt.status == 1:
            cache["polls"] = None
            cache["results"] = {}
            cache["voted_users"] = {}
            return jsonify({"success": True, "tx_hash": web3.to_hex(tx_hash)}), 200
        else:
            return jsonify({"success": False, "error": "Транзакция не была подтверждена."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/show_polls', methods=['GET'])
def show_polls():
    try:
        if cache["polls"] is None:
            cache["polls"] = contract.functions.getAllPolls().call()
        titles, all_options = cache["polls"]
        return jsonify({"titles": titles, "options": all_options}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/show_results', methods=['GET'])
def show_results():
    try:
        if cache["polls"] is None:
            cache["polls"] = contract.functions.getAllPolls().call()
        titles, all_options = cache["polls"]
        results = {}
        for i, title in enumerate(titles):
            if i not in cache["results"]:
                vote_counts = contract.functions.getResults(i).call()
                cache["results"][i] = [all_options[i], vote_counts]
            results[title] = cache["results"][i]
        return jsonify(results), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/cast_vote', methods=['POST'])
def cast_vote():
    data = request.get_json()
    poll_index = data.get('poll_index')
    option_index = data.get('option_index')
    user_email = data.get('user_email')
    account = data.get('account')
    private_key = data.get('private_key')

    if poll_index is None or option_index is None or not user_email:
        return jsonify({"success": False, "error": "Недостаточно данных."}), 400

    if not web3.is_address(account):
        return jsonify({"success": False, "error": "Некорректный адрес кошелька."}), 400

    if not is_valid_private_key(private_key):
        return jsonify({"success": False, "error": "Некорректный приватный ключ."}), 400

    if poll_index in cache["voted_users"]:
        if user_email in cache["voted_users"][poll_index]:
            return jsonify({"success": False, "error": "Вы уже проголосовали в этом опросе."}), 400
    else:
        cache["voted_users"][poll_index] = set()

    if cache["polls"] is None:
        cache["polls"] = contract.functions.getAllPolls().call()
    titles, all_options = cache["polls"]

    if poll_index >= len(titles) or option_index >= len(all_options[poll_index]):
        return jsonify({"success": False, "error": "Неверный индекс опроса или варианта."}), 400

    nonce = web3.eth.get_transaction_count(account)

    try:
        transaction = contract.functions.vote(poll_index, option_index).build_transaction({
            'chainId': 11155111,
            'gas': 200000,
            'gasPrice': web3.to_wei('20', 'gwei'),
            'nonce': nonce,
        })
        signed_txn = web3.eth.account.sign_transaction(transaction, private_key=private_key)
        tx_hash = web3.eth.send_raw_transaction(signed_txn.rawTransaction)
        tx_receipt = web3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt.status == 1:
            cache["voted_users"][poll_index].add(user_email)
            if poll_index in cache["results"]:
                del cache["results"][poll_index]
            return jsonify({"success": True, "tx_hash": web3.to_hex(tx_hash)}), 200
        else:
            return jsonify({"success": False, "error": "Транзакция не была подтверждена."}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
