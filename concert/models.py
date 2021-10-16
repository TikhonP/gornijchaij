import datetime
import hashlib
import random
from io import BytesIO
from typing import Optional

import qrcode
from PIL import Image
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, unique=True, verbose_name="the related user")
    phone = PhoneNumberField("user's phone", blank=True, null=True, help_text='Контактный телефон', default=None)
    accept_mailing = models.BooleanField("mailings allow lists", default=True)
    telegram_id = models.IntegerField("telegram user id for staff users", null=True, default=None, blank=True)

    def __str__(self):
        return "{} {}".format(self.user.username, self.phone)


# noinspection PyUnusedLocal
@receiver(post_save, sender=User)
def create_user_profile(instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


# noinspection PyUnusedLocal
@receiver(post_save, sender=User)
def save_user_profile(instance, **kwargs):
    instance.profile.save()


class Concert(models.Model):
    """Concert instance most of fields is music event schema fields https://schema.org/MusicEvent"""

    title = models.CharField("concert title", max_length=512)
    description = models.TextField("concert description", null=True, default=None, blank=True)

    start_date_time = models.DateTimeField("concert start date time")
    end_date_time = models.DateTimeField("concert end date time if required", null=True, blank=True, default=None)

    STATUS_CHOICES = [
        ('EventCancelled', 'Отменен'),
        ('EventMovedOnline', 'Перенесен в онлайн'),
        ('EventPostponed', 'Перенесен, новая дата будет назначена позже'),
        ('EventRescheduled', 'Перенесен'),
        ('EventScheduled', '')
    ]
    status = models.CharField("status", max_length=16, choices=STATUS_CHOICES, default='EventScheduled')
    """concert status assuming https://schema.org/EventStatusType EventScheduled by default"""

    place_name = models.CharField("place name", max_length=255)
    place_address = models.CharField("address of place", max_length=255)
    place_url = models.URLField("url to place page", null=True, default=None, blank=True)
    place_description = models.CharField("place description", max_length=255, null=True, blank=True)
    performer = models.CharField("artists", max_length=255, null=True, default=None, blank=True)
    organizer = models.CharField("organizer", max_length=255, null=True, blank=True, default=None)
    image = models.ImageField("concert image", upload_to="concert_images", null=True, default=None, blank=True)

    page_template = models.TextField("template to show concert page", default='<p>Добавьте страницу концерта</p>')
    email_template = models.TextField("template for email with tickets", default='<p>Добавьте страницу email</p>')
    promo_email_template = models.TextField("promo email template", null=True, blank=True, default=None)

    max_tickets_count = models.IntegerField("максимальное количество билетов", blank=True, default=None, null=True)

    yandex_notification_secret = models.CharField("yandex notification secret", max_length=255, null=True, default=None,
                                                  blank=True)

    @property
    def is_active(self) -> bool:
        if self.status != 'EventPostponed':
            if self.end_date_time:
                return timezone.now() < self.end_date_time
            return timezone.now() < self.start_date_time
        else:
            return True

    @property
    def duration(self) -> Optional[datetime.timedelta]:
        if self.end_date_time:
            return self.end_date_time - self.start_date_time

    @property
    def full_title(self) -> str:
        if self.performer:
            return self.title + ': ' + self.performer + ' в ' + self.place_name + \
                   ' | ' + self.start_date_time.strftime('%d.%y')
        else:
            return self.title + ' в ' + self.place_name + ' | ' + self.start_date_time.strftime('%d.%y')

    def get_absolute_url(self):
        return f'/concerts/{self.pk}/'

    def __str__(self) -> str:
        return "{} {}".format(self.title, "активен" if self.is_active else "Закончен")


class ConcertImage(models.Model):
    caption = models.CharField("alt text for image", max_length=255)
    image = models.ImageField("image", upload_to="concert_page_images")
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE, verbose_name="the related concert")


class Price(models.Model):
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE, verbose_name="the related concert")

    CURRENCY_CHOICES = [
        ('RUB', 'рубль'),
        ('EUR', 'евро'),
        ('USD', 'доллар'),
        ('GBP', 'британский фунт')
    ]
    price = models.FloatField("price of ticket")
    currency = models.CharField("price currency", max_length=3, choices=CURRENCY_CHOICES, default='RUB')
    description = models.CharField("price description", max_length=255)

    is_active = models.BooleanField("price active", default=True)
    max_count = models.IntegerField("price max tickets", default=None, blank=True, null=True)

    def __str__(self) -> str:
        return "{} цена - {}".format(self.concert.title, self.price)


class Transaction(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="the related user")
    concert = models.ForeignKey(Concert, on_delete=models.CASCADE, verbose_name="the related concert")

    is_done = models.BooleanField(default=False)
    date_created = models.DateTimeField("date time created", auto_now_add=True)
    date_closed = models.DateTimeField("date close", default=None, null=True)
    amount_sum = models.FloatField("amount sum", default=None, null=True)

    def __str__(self) -> str:
        return "{} {} {}".format(self.concert.title, self.user.username, "Оплачено" if self.is_done else "Не оплачено")

    def get_hash(self) -> str:
        hash_str = '{}&{}&{}'.format(self.pk, self.amount_sum, self.user.pk)
        return hashlib.sha1(hash_str.encode()).hexdigest()


class Ticket(models.Model):
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, verbose_name="the related transaction")
    price = models.ForeignKey(Price, on_delete=models.CASCADE, verbose_name="the related price")

    number = models.CharField("ticket number", max_length=6, unique=True)

    is_active = models.BooleanField("is ticket valid", default=True)

    def save(self, *args, **kwargs):
        if not self.pk:
            while True:
                self.number = str(random.randint(100000, 999999))
                if Ticket.objects.filter(number=self.number).count() == 0:
                    break

        if self.price.max_count:
            if Ticket.objects.filter(price=self.price, transaction__is_done=True).count() >= self.price.max_count:
                self.price.is_active = False
                self.price.save()

        if self.transaction.concert.max_tickets_count:
            if Ticket.objects.filter(
                    price__concert=concert, transaction__is_done=True
            ).count() >= self.transaction.concert.max_tickets_count:
                for price in Price.objects.filter(concert=concert):
                    price.is_active = False
                    price.save()

        return super(Ticket, self).save(*args, **kwargs)

    def __str__(self) -> str:
        return "{} | {} | {}".format(
            self.number, self.transaction, self.price)

    def get_hash(self) -> str:
        hash_str = '{}&{}&{}'.format(self.transaction.pk, self.price, self.number)
        return hashlib.sha1(hash_str.encode()).hexdigest()

    def get_qrcode(self) -> bytes:
        """get buffer io with qr code image for email"""

        qrcode_img = qrcode.make('{}/staff/submit/{}/{}/'.format(
            settings.HOST,
            self.number,
            self.get_hash(),
        ))
        canvas = Image.new('RGB', (500, 500), 'white')
        canvas.paste(qrcode_img)
        buffer = BytesIO()
        canvas.save(buffer, 'PNG')
        return buffer.getvalue()
