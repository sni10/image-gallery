from ..models import Favorite, Photo


class FavoriteService:
    """Adding and removing photos in a user's favorites. Both operations are idempotent."""

    @staticmethod
    def add(user, photo_id: int) -> None:
        """Raises Photo.DoesNotExist for an unknown photo."""
        photo = Photo.objects.get(pk=photo_id)
        Favorite.objects.get_or_create(user=user, photo=photo)  # handles a concurrent duplicate insert

    @staticmethod
    def remove(user, photo_id: int) -> None:
        Favorite.objects.filter(user=user, photo_id=photo_id).delete()
