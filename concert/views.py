from django.shortcuts import render
from concert.models import Concert, Price, Transaction, Ticket
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods
from concert import forms
from django.contrib.auth.models import User
from django.core import exceptions
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail
import hashlib
import datetime
from concert.sendmail import send_mail
from django.template.loader import render_to_string
# from django.conf import settings

notification_secret = '3tP6r6zJJmBVaWEvcaqqASwd' # settings.YANDEX_notification_secret

@require_http_methods(["GET"])
def main(request):
    return HttpResponse("hi")

@require_http_methods(["GET"])
def main_page(request):
    return render(request, 'main.html', {
        'concert_id': Concert.objects.all().first()
    })


@require_http_methods(["GET", "POST"])
def buy_ticket(request, concert_id):
    if concert_id is None:
        return Http404('Please provide concert id')

    concert = Concert.objects.get(id=concert_id)
    prices = Price.objects.filter(concert=concert)

    paying = False
    transaction = None

    if request.method == 'GET':
        form = forms.BuyTicketForm()

        u = request.session.get('user', False)
        if u:
            try:
                u = User.objects.get(id=u)
                p = u.profile
                print(p, p.phone)
                form = forms.BuyTicketForm({
                    'name': u.first_name,
                    'email': u.email,
                    'phone_number': p.phone,
                })
            except exceptions.ObjectDoesNotExist:
                request.session.pop('user', None)

    else:
        form = forms.BuyTicketForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            user = User.objects.filter(
                email=cd['email'], first_name=cd['name'])
            if len(user) == 0:
                user = User.objects.create(
                    username=cd['name'].replace(" ", ""),
                    first_name=cd['name'],
                    email=cd['email']
                )
                p = user.profile
                p.phone = cd['phone_number']

                user.save()
                p.save()
            else:
                user = user.first()

            request.session['user'] = user.id
            request.session['price'] = prices.first().id

            transaction = Transaction.objects.create(
                user=user,
                concert=concert
            )
            transaction.save()
            ticket = Ticket.objects.create(
                transaction = transaction,
                price = prices.first()
            )
            ticket.save()
            paying = True

    params = {
        'concert': concert,
        'price': prices.first(),
        'form': form,
        'paying': paying,
        'transaction': transaction,
    }
    return render(request, 'buy_ticket.html', params)


@csrf_exempt
@require_http_methods(["POST"])
def incoming_payment(request):
    print(request.POST)
    hash_str = "{}&{}&{}&{}&{}&{}&{}&{}&{}".format(
        request.POST.get('notification_type', ''),
        request.POST.get('operation_id', ''),
        request.POST.get('amount', ''),
        request.POST.get('currency', ''),
        request.POST.get('datetime', ''),
        request.POST.get('sender', ''),
        request.POST.get('codepro', ''),
        notification_secret,
        request.POST.get('label', ''),
    )
    hash_object = hashlib.sha1(hash_str.encode())
    print(str(hash_object.hexdigest()))
    if str(hash_object.hexdigest()) != request.POST.get('sha1_hash', ''):
        print("failed to validate hash")
        response = HttpResponse("Failed to check SHA1 hash")
        response.status_code = 400
        return response
    print("Valid sha")

    label = request.POST.get('label', '')

    try:
        transaction = Transaction.objects.get(id=int(label))
    except:
        print("transaction does not exist")
        return HttpResponse("Aborted object doesnt exist")


    # if p.price != float(request.POST['withdraw_amount']):
        # print("prices did not match")
        # return HttpResponse("Aborted price didnt match")

    transaction.date_closed = datetime.datetime.strptime(
        request.POST.get('datetime', ''), '%Y-%m-%dT%H:%M:%SZ')
    transaction.amount_sum = float(request.POST['amount'])
    transaction.is_done = True
    transaction.save()

    tickets = Ticket.objects.filter(transaction=transaction)

    u = transaction.user

    print("Transaction got!!!", transaction, u, tickets)
    try:
        msg = render_to_string("tickets_email.html", {
            'concert': transaction.concert,
            'tickets': tickets,
            'u': u,
        })
        print("generaterd html email")
        send_mail(
            'Билет на концерт {}'.format(transaction.concert.title),
            '''
                {},
                Поздравляем, {}! Вы теперь сможете попасть на этот концерт
                ---
                {}
                Обратите внимание, что на мероприятие допускаются старше 16 лет. Необходимо наличие документа удостоверяющего личность.
            '''.format(
                transaction.concert.title,
                u.first_name,
                "\n".join(["{}\n{} р. (оплачено)\nНомер - {}\n---".format(
                    i.price.description,
                    i.price.price,
                    i.number
                ) for i in tickets])
            ),
            'Gornij Chaij Ltd. <noreply@mountainteaband.ru>',
            [u.email],
            message_html=msg
        )
    except Exception as e:
        print(e)

    return HttpResponse("ok")


def done_payment(request):
    pass
