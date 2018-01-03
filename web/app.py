# -*- coding: utf8 -*-
from time import sleep
from uuid import uuid1

import requests
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from flask import Flask, render_template, redirect, request
from flask_apscheduler import APScheduler
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from requests.exceptions import RequestException


class Config(object):
    SECRET_KEY = 'go home'
    MAIL_USERNAME = '...'
    MAIL_PASSWORD = '...'
    MAIL_SERVER = 'smtp.qq.com'
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    SCHEDULER_JOBSTORES = {
        'default': SQLAlchemyJobStore(url='sqlite:///aps.db')
    }

    SCHEDULER_EXECUTORS = {
        'default': {'type': 'threadpool', 'max_workers': 20}
    }

    SCHEDULER_JOB_DEFAULTS = {
        'coalesce': False,
        'max_instances': 3
    }

    SQLALCHEMY_DATABASE_URI = 'sqlite:///aps.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class Ticket(object):
    def __init__(self, trip, date, start_time, end_time, business_seat,
                 first_seat, second_seat, soft_sleep_seat, hard_sleep_seat,
                 hard_seat, no_seat):
        self.trip = trip
        self.date = date
        self.start_time = start_time
        self.end_time = end_time
        self.business_seat = business_seat
        self.first_seat = first_seat
        self.second_seat = second_seat
        self.soft_sleep_seat = soft_sleep_seat
        self.hard_sleep_seat = hard_sleep_seat
        self.hard_sleep_seat = hard_seat
        self.no_seat = no_seat

    def __str__(self):
        return '<Train Trip {%s} Date:{%s}>' % (self.trip, self.date)

    def __getattr__(self, attr):
        if attr in type(self).__dict__:
            return
        if attr.startswith("has_") and attr.endswith('seat'):
            raw_attr = attr[4:]
            value = True if getattr(self, raw_attr) else False
            setattr(self, attr, property(
                fget=lambda x: True if getattr(x, raw_attr) else False))
            return value


app = Flask(__name__)
app.config.from_object(Config)
mail = Mail(app)
db = SQLAlchemy(app)
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()


class Station(db.Model):
    __tablename__ = 'stations'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(255))
    name = db.Column(db.String(255))

    @classmethod
    def get_code_by_name(cls, name):
        station = cls.query.filter_by(name=name).first()
        return station.code

    @classmethod
    def get_name_by_code(cls, code):
        station = cls.query.filter_by(code=code).first()
        return station.name


def check_ticket(date, start_station, end_station, recipients):
    tickets = query_tickets(date=date, start_code=start_station,
                            end_code=end_station)
    if tickets:
        with app.app_context():
            html = render_template('mail.html', tickets=tickets)
            send_mail('%s-tickets' % date, html, recipients=recipients)


def retry(max_times=3):
    def wrapper(func):
        def decorate(*args, **kwargs):
            error = None
            for _ in range(max_times):
                sleep(2)
                try:
                    return_value = func(*args, **kwargs)
                except Exception as e:
                    error = e
                else:
                    if return_value:
                        return return_value
            if error:
                raise error

        return decorate

    return wrapper


query_url_fmt = ("https://kyfw.12306.cn/otn/{query_route}"
                 "?leftTicketDTO.train_date={date}"
                 "&leftTicketDTO.from_station={start_code}"
                 "&leftTicketDTO.to_station={end_code}&purpose_codes=ADULT")


@retry(max_times=3)
def query_tickets(date, start_code, end_code):
    try:
        query_url = get_query_url(date, start_code, end_code)
        response = requests.get(query_url, allow_redirects=False, verify=False)
        tickets_infos = response.json()['data']['result']
    except RequestException:
        raise
    except Exception as e:
        return []
    else:
        tickets = []
        for ticket_info in tickets_infos:
            ticket_info = ticket_info.split('|')
            ticket = Ticket(date=date, trip=ticket_info[3],
                            start_time=ticket_info[8],
                            end_time=ticket_info[9],
                            business_seat=ticket_info[-5],
                            second_seat=ticket_info[-7],
                            first_seat=ticket_info[-6],
                            soft_sleep_seat=ticket_info[-14],
                            hard_sleep_seat=ticket_info[-9],
                            hard_seat=ticket_info[-8], no_seat=ticket_info[-11])
            tickets.append(ticket)
        return tickets


def get_query_url(date, start_code, end_code):
    query_url = query_url_fmt.format(query_route='leftTicket/query', date=date,
                                     start_code=start_code, end_code=end_code)
    try:
        response = requests.get(query_url, allow_redirects=False, verify=False)
        query_route = response.json()['c_url']
    except RequestException:
        raise
    except Exception:
        return query_url
    return query_url_fmt.format(query_route=query_route, date=date,
                                start_code=start_code, end_code=end_code)


def send_mail(subject, html, recipients):
    msg = Message(subject, html=html, sender='1593487967@qq.com',
                  recipients=recipients)
    mail.send(msg)


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        date = request.form['date']
        start = Station.get_code_by_name(request.form['start_station'])
        end = Station.get_code_by_name(request.form['end_station'])
        email = request.form['email']
        scheduler.add_job(str(uuid1()), check_ticket,
                          args=(date, start, end, [email]), trigger='interval',
                          seconds=60)
        return redirect('/ok')
    else:
        return render_template('form.html')


@app.route('/ok', methods=['GET', 'POST'])
def ok():
    return "OK"


if __name__ == '__main__':
    app.run(debug=True)
