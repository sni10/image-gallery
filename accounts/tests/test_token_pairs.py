import threading
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, TransactionTestCase

from ..models import RefreshToken
from ..services.access_tokens import AccessTokenService
from ..services.token_pairs import InvalidRefreshToken, TokenPairService


class TokenPairServiceTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        self.service = TokenPairService()

    def test_issue(self):
        pair = self.service.issue(self.user)
        self.assertEqual(AccessTokenService().verify(pair.access), self.user.pk)
        stored = RefreshToken.objects.get()
        self.assertNotEqual(stored.token_hash, pair.refresh)  # only the hash is stored
        self.assertFalse(RefreshToken.objects.filter(token_hash=pair.refresh).exists())

    def test_rotate(self):
        first = self.service.issue(self.user)
        second = self.service.rotate(first.refresh)
        self.assertNotEqual(first.refresh, second.refresh)
        self.assertEqual(AccessTokenService().verify(second.access), self.user.pk)
        families = set(RefreshToken.objects.values_list('family', flat=True))
        self.assertEqual(len(families), 1)  # rotation stays in the login's family

    def test_reuse_revokes_all_tokens_of_user(self):
        first = self.service.issue(self.user)
        second = self.service.rotate(first.refresh)
        other_session = self.service.issue(self.user)
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate(first.refresh)  # replay of an already rotated token
        for raw in (second.refresh, other_session.refresh):
            with self.assertRaises(InvalidRefreshToken):
                self.service.rotate(raw)

    def test_expired_unknown_inactive(self):
        expired = TokenPairService(refresh_lifetime=timedelta(seconds=-1)).issue(self.user)
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate(expired.refresh)
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate('made-up')
        pair = self.service.issue(self.user)
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate(pair.refresh)

    def test_revoke_one_and_all(self):
        a, b, c = (self.service.issue(self.user) for _ in range(3))
        self.service.revoke(a.refresh)
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate(a.refresh)  # logged-out token is rejected, but it is not a reuse
        self.service.rotate(b.refresh)  # other sessions still work
        self.service.revoke_all(self.user)
        with self.assertRaises(InvalidRefreshToken):
            self.service.rotate(c.refresh)

    def test_issue_cleans_expired(self):
        TokenPairService(refresh_lifetime=timedelta(seconds=-1)).issue(self.user)
        self.service.issue(self.user)
        self.assertEqual(RefreshToken.objects.count(), 1)


class ConcurrentRotationTest(TransactionTestCase):
    def test_parallel_exchange_of_one_token_succeeds_once(self):
        user = User.objects.create_user('anna@example.com', 'anna@example.com', 'x')
        raw = TokenPairService().issue(user).refresh
        results, barrier = [], threading.Barrier(2)

        def exchange():
            barrier.wait()
            try:
                TokenPairService().rotate(raw)
                results.append('ok')
            except InvalidRefreshToken:
                results.append('rejected')
            finally:
                connection.close()

        threads = [threading.Thread(target=exchange) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sorted(results), ['ok', 'rejected'])
