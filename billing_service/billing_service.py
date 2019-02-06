import atexit
import time
import json
import os
import uuid

from redis import StrictRedis
from flask import request
from flask import Flask

import requests

from lib.common import log_error, log_info
from lib.event_store import Event, EventStore


class Billing(object):
    """
    Billing Entity class.
    """

    def __init__(self, _order_id):
        self.id = str(uuid.uuid4())
        self.order_id = _order_id
        self.done = time.time()


app = Flask(__name__)
redis = StrictRedis(decode_responses=True, host='redis')
store = EventStore(redis)


def order_created(item):
    try:
        msg_data = json.loads(item[1][0][1]['entity'])
        customer = store.find_one('customer', msg_data['customer_id'])
        products = [store.find_one('product', product_id) for product_id in msg_data['product_ids']]
        msg = """Dear {}!

Please transfer € {} with your favourite payment method.

Cheers""".format(customer['name'], sum([int(product['price']) for product in products]))

        requests.post('http://msg-service:5000/email', json={
            "to": customer['email'],
            "msg": msg
        })
    except Exception as e:
        log_error(e)


def billing_created(item):
    try:
        msg_data = json.loads(item[1][0][1]['entity'])
        order = store.find_one('order', msg_data['order_id'])
        customer = store.find_one('customer', order['customer_id'])
        products = [store.find_one('product', product_id) for product_id in order['product_ids']]
        msg = """Dear {}!

We've just received € {} from you, thank you for your transfer.

Cheers""".format(customer['name'], sum([int(product['price']) for product in products]))

        requests.post('http://msg-service:5000/email', json={
            "to": customer['email'],
            "msg": msg
        })
    except Exception as e:
        log_error(e)


def subscribe():
    store.subscribe('order', 'created', order_created)
    store.subscribe('billing', 'created', billing_created)
    log_info('subscribed to channels')


def unsubscribe():
    store.unsubscribe('order', 'created', order_created)
    store.unsubscribe('billing', 'created', billing_created)
    log_info('unsubscribed from channels')


if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    store.subscribe_to_entity_events('billing')
    atexit.register(store.unsubscribe_from_entity_events, 'billing')
    subscribe()
    atexit.register(unsubscribe)


@app.route('/billings', methods=['GET'])
@app.route('/billing/<billing_id>', methods=['GET'])
def get(billing_id=None):

    if billing_id:
        billing = store.find_one('billing', billing_id)
        if not billing:
            raise ValueError("could not find billing")

        return json.dumps(billing) if billing else json.dumps(False)
    else:
        return json.dumps([item for item in store.find_all('billing').values()])


@app.route('/billing', methods=['POST'])
@app.route('/billings', methods=['POST'])
def post():

    values = request.get_json()
    if not isinstance(values, list):
        values = [values]

    billing_ids = []
    for value in values:
        try:
            new_billing = Billing(value['order_id'])
        except KeyError:
            raise ValueError("missing mandatory parameter 'order_id'")

        # trigger event
        store.publish(Event('billing', 'created', **new_billing.__dict__))

        billing_ids.append(new_billing.id)

    return json.dumps(billing_ids)


@app.route('/billing/<billing_id>', methods=['PUT'])
def put(billing_id):

    value = request.get_json()
    try:
        billing = Billing(value['order_id'])
    except KeyError:
        raise ValueError("missing mandatory parameter 'order_id'")

    billing.id = billing_id

    # trigger event
    store.publish(Event('billing', 'updated', **billing.__dict__))

    return json.dumps(True)


@app.route('/billing/<billing_id>', methods=['DELETE'])
def delete(billing_id):

    billing = store.find_one('billing', billing_id)
    if billing:

        # trigger event
        store.publish(Event('billing', 'deleted', **billing))

        return json.dumps(True)
    else:
        raise ValueError("could not find billing")
