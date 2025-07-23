from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.utils.text import slugify
from shortuuid.django_fields import ShortUUIDField
import shortuuid

# ----------------- User -------------------
class User(AbstractUser):
    username = models.CharField(unique=True, max_length=100)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    otp = models.CharField(max_length=10, blank=True, null=True)
    reset_token = models.CharField(max_length=255, blank=True, null=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        email_username, _ = self.email.split('@') if '@' in self.email else (self.email, '')
        if not self.full_name:
            self.full_name = email_username
        if not self.username:
            self.username = email_username
        super().save(*args, **kwargs)


# ----------------- Profile -------------------
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    image = models.FileField(upload_to="image", default="default/default.user.jpg", null=True, blank=True)
    full_name = models.CharField(max_length=100, null=True, blank=True)
    bio = models.CharField(max_length=100, null=True, blank=True)
    about = models.CharField(max_length=100, null=True, blank=True)
    author = models.BooleanField(default=False)
    Country = models.CharField(max_length=100, null=True, blank=True)
    facebook = models.CharField(max_length=100, null=True, blank=True)
    twitter = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.user.username

    def save(self, *args, **kwargs):
        if not self.full_name:
            self.full_name = self.user.full_name
        super().save(*args, **kwargs)


def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)


def save_user_profile(sender, instance, **kwargs):
    # Ensure profile exists before saving to avoid errors
    if hasattr(instance, 'profile'):
        instance.profile.save()


post_save.connect(create_user_profile, sender=User)
post_save.connect(save_user_profile, sender=User)


# ----------------- Category -------------------
class Category(models.Model):
    title = models.CharField(max_length=100)
    image = models.FileField(upload_to="image", null=True, blank=True)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def post_count(self):
        from api.models import Post
        return Post.objects.filter(category=self).count()


# ----------------- Post -------------------
class Post(models.Model):
    STATUS = (
        ("Active", "Active"),
        ("Draft", "Draft"),
        ("Disable", "Disable"),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="posts", default=1)
    title = models.CharField(max_length=100)
    tags = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    image = models.FileField(upload_to="image", null=True, blank=True)
    status = models.CharField(max_length=100, choices=STATUS, default="Active")
    views = models.IntegerField(default=0)
    likes = models.ManyToManyField(User, related_name="likes_user", blank=True)
    slug = models.SlugField(unique=True, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Posts"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title) + shortuuid.uuid()[:2]
        super().save(*args, **kwargs)

    def comments(self):
        from api.models import Comment
        return Comment.objects.filter(post=self)


# ----------------- Comment -------------------
class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='comments_made') # Added optional user field
    name = models.CharField(max_length=100)
    email = models.CharField(max_length=100)
    comment = models.TextField(null=True, blank=True)
    reply = models.TextField(null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.post.title

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Comment"


# ----------------- Bookmark -------------------
class Bookmark(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.post.title

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Bookmark"


# ----------------- Notification -------------------
class Notification(models.Model):
    NOTI_TYPE = (
        ("Like", "Like"),
        ("Comment", "Comment"),
        ("Bookmark", "Bookmark"),
        # Add other notification types if needed (e.g., "New Post", "Follow")
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications_received") # The user *receiving* the notification
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications_sent", help_text="The user who performed the action (e.g., liked, commented)") # <--- ADDED THIS FIELD
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True) # Allow null if some notifications might not be post-related
    type = models.CharField(max_length=100, choices=NOTI_TYPE, default="Like")
    seen = models.BooleanField(default=False)
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        # Improved __str__ for better readability
        if self.post:
            return f"{self.type} on '{self.post.title}' by {self.actor.username if self.actor else 'Unknown'} to {self.user.username}"
        return f"{self.type} notification to {self.user.username}"

    class Meta:
        ordering = ['-date']
        verbose_name_plural = "Notifications" # Corrected pluralization