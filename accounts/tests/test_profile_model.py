import importlib

from django.apps import apps
from django.contrib.auth.models import User
from django.test import TestCase

from common.public_ids import make_public_id

from ..models import Profile

migration = importlib.import_module('accounts.migrations.0002_profile')


class ProfileTest(TestCase):
    def test_new_user_gets_profile_with_public_id(self):
        user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.link_date, user.date_joined)
        self.assertEqual(profile.public_id, make_public_id('accounts.profile', profile.pk, user.date_joined))
        self.assertRegex(profile.public_id, r'^[a-z2-7]{26}$')

    def test_migration_creates_profiles_for_existing_users(self):
        user = User.objects.create_user('old@example.com', 'old@example.com', 'x')
        Profile.objects.filter(user=user).delete()  # as if the user existed before profiles
        migration.create_profiles(apps, None)
        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.link_date, user.date_joined)
        self.assertEqual(profile.public_id, make_public_id('accounts.profile', profile.pk, user.date_joined))
