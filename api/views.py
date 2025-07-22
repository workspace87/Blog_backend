from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Sum
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

import random

from api import serializer as api_serializer
from api import models as api_models


def home(request):
    return HttpResponse("Welcome to the blog backend!")


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = api_serializer.MyTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    queryset = api_models.User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.RegisterSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.ProfileSerializer

    def get_object(self):
        user_id = self.kwargs['user_id']
        try:
            user = api_models.User.objects.get(id=user_id)
            profile = api_models.Profile.objects.get(user=user)
            return profile
        except api_models.User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User not found.")
        except api_models.Profile.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Profile not found for this user.")


def generate_numeric_otp(length=7):
    return ''.join(str(random.randint(0, 9)) for _ in range(length))


class PasswordEmailVerify(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.UserSerializer

    def get_object(self):
        email = self.kwargs['email']
        try:
            user = api_models.User.objects.get(email=email)
        except api_models.User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User with this email does not exist.")

        user.otp = generate_numeric_otp()
        uidb64 = user.pk

        refresh = RefreshToken.for_user(user)
        reset_token = str(refresh.access_token)

        user.reset_token = reset_token
        user.save()

        link = f"http://localhost:5173/create-new-password?otp={user.otp}&uidb64={uidb64}&reset_token={reset_token}"

        merge_data = {
            'link': link,
            'username': user.username,
        }
        subject = "Password Reset Request"
        text_body = render_to_string("email/password_reset.txt", merge_data)
        html_body = render_to_string("email/password_reset.html", merge_data)

        msg = EmailMultiAlternatives(
            subject=subject,
            from_email=settings.FROM_EMAIL,
            to=[user.email],
            body=text_body
        )
        msg.attach_alternative(html_body, "text/html")
        msg.send()

        return user


class PasswordChangeView(generics.CreateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.UserSerializer

    def create(self, request, *args, **kwargs):
        payload = request.data

        otp = payload.get('otp')
        uidb64 = payload.get('uidb64')
        password = payload.get('password')
        reset_token = payload.get('reset_token')

        if not all([otp, uidb64, password, reset_token]):
            return Response(
                {"message": "Missing required fields."},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            user = api_models.User.objects.get(id=uidb64, otp=otp, reset_token=reset_token)
        except api_models.User.DoesNotExist:
            return Response(
                {"message": "Invalid OTP, reset token, or user ID."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(password)
        user.otp = ""
        user.reset_token = ""
        user.save()

        return Response({"message": "Password Changed Successfully"}, status=status.HTTP_201_CREATED)


######################## Post APIs ########################


class CategoryListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.CategorySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return api_models.Category.objects.all()


class PostCategoryListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        category_slug = self.kwargs['category_slug']
        try:
            category = api_models.Category.objects.get(slug=category_slug)
        except api_models.Category.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Category not found.")
        return api_models.Post.objects.filter(category=category, status="Active")


class PostListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return api_models.Post.objects.all()


class PostDetailAPIView(generics.RetrieveAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        slug = self.kwargs['slug']
        try:
            post = api_models.Post.objects.get(slug=slug, status="Active")
        except api_models.Post.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Post not found or inactive.")
        post.views += 1
        post.save()
        return post


class LikePostAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'post_id': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        user_id = request.data.get('user_id')
        post_id = request.data.get('post_id')

        if not all([user_id, post_id]):
            return Response({"message": "Missing user_id or post_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = api_models.User.objects.get(id=user_id)
            post = api_models.Post.objects.get(id=post_id)
        except (api_models.User.DoesNotExist, api_models.Post.DoesNotExist):
            return Response({"message": "User or Post not found."}, status=status.HTTP_404_NOT_FOUND)

        if user in post.likes.all():
            post.likes.remove(user)
            return Response({"message": "Post Disliked"}, status=status.HTTP_200_OK)
        else:
            post.likes.add(user)
            api_models.Notification.objects.create(
                user=post.user,
                post=post,
                type="Like",
            )
            return Response({"message": "Post Liked"}, status=status.HTTP_201_CREATED)


class PostCommentAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'post_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'comment': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        post_id = request.data.get('post_id')
        name = request.data.get('name')
        email = request.data.get('email')
        comment = request.data.get('comment')

        if not all([post_id, name, email, comment]):
            return Response({"message": "Missing fields in request."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            post = api_models.Post.objects.get(id=post_id)
        except api_models.Post.DoesNotExist:
            return Response({"message": "Post not found."}, status=status.HTTP_404_NOT_FOUND)

        api_models.Comment.objects.create(
            post=post,
            name=name,
            email=email,
            comment=comment,
        )

        api_models.Notification.objects.create(
            user=post.user,
            post=post,
            type="Comment",
        )

        return Response({"message": "Comment Sent"}, status=status.HTTP_201_CREATED)


class BookmarkPostAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'post_id': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        user_id = request.data.get('user_id')
        post_id = request.data.get('post_id')

        if not all([user_id, post_id]):
            return Response({"message": "Missing user_id or post_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = api_models.User.objects.get(id=user_id)
            post = api_models.Post.objects.get(id=post_id)
        except (api_models.User.DoesNotExist, api_models.Post.DoesNotExist):
            return Response({"message": "User or Post not found."}, status=status.HTTP_404_NOT_FOUND)

        bookmark = api_models.Bookmark.objects.filter(post=post, user=user).first()
        if bookmark:
            bookmark.delete()
            return Response({"message": "Post Un-Bookmarked"}, status=status.HTTP_200_OK)
        else:
            api_models.Bookmark.objects.create(user=user, post=post)
            api_models.Notification.objects.create(
                user=post.user,
                post=post,
                type="Bookmark",
            )
            return Response({"message": "Post Bookmarked"}, status=status.HTTP_201_CREATED)


######################## Author Dashboard APIs ########################

class DashboardStats(generics.ListAPIView):
    serializer_class = api_serializer.AuthorStats
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_id = self.kwargs.get('user_id')
        try:
            user = api_models.User.objects.get(id=user_id)
        except api_models.User.DoesNotExist:
            return []

        posts = api_models.Post.objects.filter(user=user)
        views = posts.aggregate(view_count=Sum("views"))['view_count'] or 0
        posts_count = posts.count()
        likes = sum(post.likes.count() for post in posts)
        bookmarks = api_models.Bookmark.objects.filter(user=user).count()

        return [{
            "views": views,
            "posts": posts_count,
            "likes": likes,
            "bookmarks": bookmarks,
        }]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        if not queryset:
            return Response({"error": "User not found or no data available."}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class DashboardPostLists(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        try:
            user = api_models.User.objects.get(id=user_id)
        except api_models.User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User not found.")
        return api_models.Post.objects.filter(user=user).order_by("-id")


class DashboardCommentLists(generics.ListAPIView):
    serializer_class = api_serializer.CommentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return api_models.Comment.objects.all()


class DashboardNotificationLists(generics.ListAPIView):
    serializer_class = api_serializer.NotificationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user_id = self.kwargs['user_id']
        try:
            user = api_models.User.objects.get(id=user_id)
        except api_models.User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User not found.")
        return api_models.Notification.objects.filter(seen=False, user=user)


class DashboardMarkNotiSeenAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'noti_id': openapi.Schema(type=openapi.TYPE_INTEGER),
            },
        ),
    )
    def post(self, request):
        noti_id = request.data.get('noti_id')

        if not noti_id:
            return Response({"message": "Missing notification ID."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            noti = api_models.Notification.objects.get(id=noti_id)
        except api_models.Notification.DoesNotExist:
            return Response({"message": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)

        noti.seen = True
        noti.save()
        return Response({"message": "Notification marked as seen."}, status=status.HTTP_200_OK)


class DashboardPostCommentAPIView(APIView):
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'comment_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'reply': openapi.Schema(type=openapi.TYPE_STRING),
            },
        ),
    )
    def post(self, request):
        comment_id = request.data.get('comment_id')
        reply = request.data.get('reply')

        if not all([comment_id, reply]):
            return Response({"message": "Missing comment_id or reply."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            comment = api_models.Comment.objects.get(id=comment_id)
        except api_models.Comment.DoesNotExist:
            return Response({"message": "Comment not found."}, status=status.HTTP_404_NOT_FOUND)

        comment.reply = reply
        comment.save()

        return Response({"message": "Comment response sent."}, status=status.HTTP_201_CREATED)


class DashboardPostCreateAPIView(generics.CreateAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        user_id = request.data.get('user_id')
        title = request.data.get('title')
        image = request.data.get('image')
        description = request.data.get('description')
        tags = request.data.get('tags')
        category_id = request.data.get('category')
        post_status = request.data.get('post_status')

        if not all([user_id, title, category_id, post_status]):
            return Response({"message": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = api_models.User.objects.get(id=user_id)
            category = api_models.Category.objects.get(id=category_id)
        except (api_models.User.DoesNotExist, api_models.Category.DoesNotExist):
            return Response({"message": "User or Category not found."}, status=status.HTTP_404_NOT_FOUND)

        post = api_models.Post.objects.create(
            user=user,
            title=title,
            image=image,
            description=description,
            tags=tags,
            category=category,
            status=post_status
        )

        return Response({"message": "Post created successfully."}, status=status.HTTP_201_CREATED)


class DashboardPostEditAPIView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        user_id = self.kwargs['user_id']
        post_id = self.kwargs['post_id']

        try:
            user = api_models.User.objects.get(id=user_id)
        except api_models.User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("User not found.")

        try:
            post = api_models.Post.objects.get(user=user, id=post_id)
            return post
        except api_models.Post.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound("Post not found for this user.")

    def update(self, request, *args, **kwargs):
        post_instance = self.get_object()

        title = request.data.get('title')
        image = request.data.get('image')
        description = request.data.get('description')
        tags = request.data.get('tags')
        category_id = request.data.get('category')
        post_status = request.data.get('post_status')

        if not all([title, category_id, post_status]):
            return Response({"message": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            category = api_models.Category.objects.get(id=category_id)
        except api_models.Category.DoesNotExist:
            return Response({"message": "Category not found."}, status=status.HTTP_404_NOT_FOUND)

        post_instance.title = title
        if image != "undefined" and image is not None:
            post_instance.image = image
        post_instance.description = description
        post_instance.tags = tags
        post_instance.category = category
        post_instance.status = post_status
        post_instance.save()

        return Response({"message": "Post updated successfully."}, status=status.HTTP_200_OK)