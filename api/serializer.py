from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers

from api import models as api_models

# Custom JWT Token Serializer
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['full_name'] = user.full_name
        token['email'] = user.email
        token['username'] = user.username
        # Safely access vendor_id if exists; fallback to None or 0 as needed
        token['vendor_id'] = getattr(getattr(user, 'vendor', None), 'id', 0)
        return token

# User Registration Serializer with password confirmation and validation
class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = api_models.User
        fields = ('full_name', 'email', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})
        return attrs

    def create(self, validated_data):
        # Pop password2 as it's not needed for user model creation
        validated_data.pop('password2', None)
        user = api_models.User.objects.create(
            full_name=validated_data.get('full_name'),
            email=validated_data.get('email'),
        )
        # Assign username from email handle if not set already (handle safely)
        if user.email and '@' in user.email:
            user.username = user.email.split('@')[0]
        user.set_password(validated_data.get('password'))
        user.save()
        return user

# User Serializer - all fields included
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = api_models.User
        fields = '__all__'

# Profile Serializer - include nested user data in output representation
class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = api_models.Profile
        fields = '__all__'

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['user'] = UserSerializer(instance.user).data
        return response

# Password reset serializer for just email input
class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()

# Category Serializer with post count and dynamic depth setting
class CategorySerializer(serializers.ModelSerializer):
    post_count = serializers.SerializerMethodField()

    class Meta:
        model = api_models.Category
        fields = [
            "id",
            "title",
            "image",
            "slug",
            "post_count",
        ]
        depth = 3  # Default depth

    def get_post_count(self, category):
        return category.posts.count()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request', None)
        if request and request.method == 'POST':
            self.Meta.depth = 0

# Comment Serializer with dynamic depth setting
class CommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = api_models.Comment
        fields = "__all__"
        depth = 1  # Default depth

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request', None)
        if request and request.method == 'POST':
            self.Meta.depth = 0

# Post Serializer with comments nested and likes count field
class PostSerializer(serializers.ModelSerializer):
    comments = CommentSerializer(many=True, read_only=True)
    likes_count = serializers.SerializerMethodField()

    class Meta:
        model = api_models.Post
        fields = "__all__"
        depth = 3  # Default depth

    def get_likes_count(self, obj):
        return obj.likes.count()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request', None)
        if request and request.method == 'POST':
            self.Meta.depth = 0

# Bookmark Serializer with dynamic depth
class BookmarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = api_models.Bookmark
        fields = "__all__"
        depth = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request', None)
        if request and request.method == 'POST':
            self.Meta.depth = 0

# Notification Serializer with dynamic depth
class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = api_models.Notification
        fields = "__all__"
        depth = 3

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request', None)
        if request and request.method == 'POST':
            self.Meta.depth = 0

# Serializer for aggregated author statistics (non-model serializer)
class AuthorStats(serializers.Serializer):
    views = serializers.IntegerField(default=0)
    posts = serializers.IntegerField(default=0)
    likes = serializers.IntegerField(default=0)
    bookmarks = serializers.IntegerField(default=0)