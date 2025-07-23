from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Sum
from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.permissions import AllowAny, IsAuthenticated # ADD IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema

from rest_framework.decorators import api_view, permission_classes

import random

from api import serializer as api_serializer
from api import models as api_models
from django.shortcuts import get_object_or_404

@api_view(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']) # Allow all methods for flexibility
@permission_classes([AllowAny]) # Often 404s should be publicly accessible
def custom_404_view(request, exception=None):
    """
    Custom 404 Not Found view for API endpoints.
    """
    return Response(
        {"detail": "The requested resource was not found.", "status_code": 404},
        status=status.HTTP_404_NOT_FOUND
    )


def home(request):
    return HttpResponse("Welcome to the blog backend!")


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = api_serializer.MyTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    queryset = api_models.User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = api_serializer.RegisterSerializer


class ProfileView(generics.RetrieveUpdateAPIView):
    # Changed to IsAuthenticated for a profile view as it's sensitive data
    permission_classes = [IsAuthenticated] # Changed from AllowAny
    serializer_class = api_serializer.ProfileSerializer

    def get_object(self):
        # Using request.user if no user_id is provided in URL, or fallback to URL user_id
        # if the profile is meant to be publicly viewable (read-only)
        # For sensitive operations like update, request.user should be used
        user_id = self.kwargs.get('user_id')
        if not user_id:
            user = self.request.user # Use the authenticated user
        else:
            # If user_id is in URL, ensure it matches the authenticated user for updates
            # or simply allow retrieving any profile but restrict updates
            if self.request.user.is_authenticated and str(self.request.user.id) != user_id:
                # You might want to allow viewing other profiles but restrict editing
                # For this example, if user_id is passed, we fetch that user.
                # If it's for updating, the permission class should ensure ownership.
                pass # The get_object_or_404 below will handle if user doesn't exist

        user = get_object_or_404(api_models.User, id=user_id)
        profile = get_object_or_404(api_models.Profile, user=user)
        
        # Ownership check for update operation
        if self.request.method in ['PUT', 'PATCH'] and self.request.user != user:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("You do not have permission to edit this profile.")
            
        return profile


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

        # IMPORTANT: For live app, replace localhost:5173 with your actual frontend domain
        # This link needs to be accessible from where the user opens the email.
        link = f"{settings.FRONTEND_URL}/create-new-password?otp={user.otp}&uidb64={uidb64}&reset_token={reset_token}"

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
        # Use get_object_or_404 for cleaner handling of non-existent category
        category = get_object_or_404(api_models.Category, slug=category_slug)
        return api_models.Post.objects.filter(category=category, status="Active")


class PostListAPIView(generics.ListAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return api_models.Post.objects.filter(status="Active") # Only show active posts


class PostDetailAPIView(generics.RetrieveAPIView):
    serializer_class = api_serializer.PostSerializer
    permission_classes = [AllowAny]

    def get_object(self):
        slug = self.kwargs['slug']
        # Use get_object_or_404 for cleaner handling
        post = get_object_or_404(api_models.Post, slug=slug, status="Active")
        post.views += 1
        post.save()
        return post


class LikePostAPIView(APIView):
    permission_classes = [IsAuthenticated] # Only authenticated users can like/unlike

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                # user_id is no longer needed in request body, as it comes from auth token
                'post_id': openapi.Schema(type=openapi.TYPE_STRING, description="ID of the post to like/unlike"),
            },
            required=['post_id']
        ),
        responses={
            200: openapi.Response("Success", api_serializer.LikePostResponseSerializer),
            201: openapi.Response("Created", api_serializer.LikePostResponseSerializer),
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        }
    )
    def post(self, request):
        post_id = request.data.get('post_id')
        user = request.user # Get the authenticated user from the token

        if not post_id:
            return Response({"message": "Post ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Use get_object_or_404 for cleaner error handling if post doesn't exist
        post = get_object_or_404(api_models.Post, id=post_id)

        liked = False
        if user in post.likes.all():
            post.likes.remove(user)
            # Delete notification if the user unlikes the post
            api_models.Notification.objects.filter(
                user=post.user,
                post=post,
                type="Like",
                actor=user # Assuming you add an 'actor' field to Notification model to track who did the action
            ).delete()
            message = "Post Disliked"
        else:
            post.likes.add(user)
            liked = True
            message = "Post Liked"
            # Create notification only if the post author is not the one liking their own post
            if user != post.user:
                api_models.Notification.objects.create(
                    user=post.user,
                    post=post,
                    type="Like",
                    actor=user # Add 'actor' to track who liked it
                )
        
        # Return current like status and count for frontend to update UI
        return Response({
            "message": message,
            "liked": liked,
            "likes_count": post.likes.count()
        }, status=status.HTTP_200_OK if not liked else status.HTTP_201_CREATED)


class PostCommentAPIView(APIView):
    permission_classes = [AllowAny] # Keeping AllowAny for comments as per previous. If users must be logged in to comment, change to IsAuthenticated
    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'post_id': openapi.Schema(type=openapi.TYPE_INTEGER),
                'name': openapi.Schema(type=openapi.TYPE_STRING),
                'email': openapi.Schema(type=openapi.TYPE_STRING),
                'comment': openapi.Schema(type=openapi.TYPE_STRING),
                'user_id': openapi.Schema(type=openapi.TYPE_INTEGER, description="Optional: ID of the authenticated user if commenting as registered user"),
            },
        ),
    )
    def post(self, request):
        post_id = request.data.get('post_id')
        name = request.data.get('name')
        email = request.data.get('email')
        comment_text = request.data.get('comment') # Renamed to avoid conflict with model field name
        user_id = request.data.get('user_id') # Optional user ID for comments

        if not all([post_id, name, email, comment_text]):
            return Response({"message": "Missing fields in request."}, status=status.HTTP_400_BAD_REQUEST)

        post = get_object_or_404(api_models.Post, id=post_id)
        
        user_instance = None
        if user_id:
            user_instance = get_object_or_404(api_models.User, id=user_id)
            # If authenticated, you might want to auto-fill name/email from user profile
            # or require user to be authenticated if user_id is provided.
            # For now, it's just an optional field to link the comment to a user.


        api_models.Comment.objects.create(
            post=post,
            user=user_instance, # Link the user if provided
            name=name,
            email=email,
            comment=comment_text,
        )

        api_models.Notification.objects.create(
            user=post.user, # The author of the post
            post=post,
            type="Comment",
            actor=user_instance # The user who commented
        )

        return Response({"message": "Comment Sent"}, status=status.HTTP_201_CREATED)


class BookmarkPostAPIView(APIView):
    permission_classes = [IsAuthenticated] # Only authenticated users can bookmark/unbookmark

    @swagger_auto_schema(
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'post_id': openapi.Schema(type=openapi.TYPE_STRING, description="ID of the post to bookmark/unbookmark"),
            },
            required=['post_id']
        ),
        responses={
            200: "Success",
            201: "Created",
            400: "Bad Request",
            401: "Unauthorized",
            404: "Not Found",
        }
    )
    def post(self, request):
        post_id = request.data.get('post_id')
        user = request.user # Get the authenticated user from the token

        if not post_id:
            return Response({"message": "Post ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        post = get_object_or_404(api_models.Post, id=post_id)

        bookmark = api_models.Bookmark.objects.filter(post=post, user=user).first()
        if bookmark:
            bookmark.delete()
            # Delete notification for bookmark
            api_models.Notification.objects.filter(
                user=post.user,
                post=post,
                type="Bookmark",
                actor=user
            ).delete()
            return Response({"message": "Post Un-Bookmarked", "bookmarked": False}, status=status.HTTP_200_OK)
        else:
            api_models.Bookmark.objects.create(user=user, post=post)
            # Create notification only if the post author is not the one bookmarking their own post
            if user != post.user:
                api_models.Notification.objects.create(
                    user=post.user,
                    post=post,
                    type="Bookmark",
                    actor=user
                )
            return Response({"message": "Post Bookmarked", "bookmarked": True}, status=status.HTTP_201_CREATED)


######################## Author Dashboard APIs ########################

class DashboardStats(generics.ListAPIView):
    permission_classes = [IsAuthenticated] # Dashboard stats should be for authenticated users only
    serializer_class = api_serializer.AuthorStats

    def get_queryset(self):
        # The user_id from URL is redundant if permission_classes is IsAuthenticated.
        # It should usually just be request.user.
        # However, if this endpoint is meant to fetch stats for *any* user (e.g., public profile stats),
        # then AllowAny might be appropriate, but then the security risk increases.
        # Assuming DashboardStats is for the logged-in user:
        user = self.request.user # Get the authenticated user
        
        # If the URL still expects user_id for public profiles, you'd do:
        # user_id_from_url = self.kwargs.get('user_id')
        # user = get_object_or_404(api_models.User, id=user_id_from_url)
        # However, for 'DashboardStats', it usually implies the logged-in user's stats.
        
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
        # No need for user_id in URL for this if it's for the authenticated user's dashboard
        # If user is not found (e.g., not authenticated, or an issue with request.user),
        # IsAuthenticated will handle it before reaching here.
        queryset = self.get_queryset()
        # The serializer should handle the structure correctly, no need for manual 404 for empty list.
        # If get_queryset returns an empty list, it means the authenticated user has no posts/data,
        # which is a valid 200 response with empty data, not a 404 for the user.
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class DashboardPostLists(generics.ListAPIView):
    permission_classes = [IsAuthenticated] # Should be for authenticated user
    serializer_class = api_serializer.PostSerializer

    def get_queryset(self):
        # Again, use request.user instead of URL user_id for authenticated user's dashboard
        user = self.request.user
        return api_models.Post.objects.filter(user=user).order_by("-id")


class DashboardCommentLists(generics.ListAPIView):
    permission_classes = [IsAuthenticated] # Comments on authenticated user's posts
    serializer_class = api_serializer.CommentSerializer

    def get_queryset(self):
        # Fetch comments on posts authored by the authenticated user
        user = self.request.user
        return api_models.Comment.objects.filter(post__user=user).order_by("-id")


class DashboardNotificationLists(generics.ListAPIView):
    permission_classes = [IsAuthenticated] # Notifications for authenticated user
    serializer_class = api_serializer.NotificationSerializer

    def get_queryset(self):
        user = self.request.user
        return api_models.Notification.objects.filter(seen=False, user=user).order_by("-id")


class DashboardMarkNotiSeenAPIView(APIView):
    permission_classes = [IsAuthenticated] # Mark notification seen for authenticated user
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
        user = request.user # Authenticated user

        if not noti_id:
            return Response({"message": "Missing notification ID."}, status=status.HTTP_400_BAD_REQUEST)
        
        # Ensure the notification belongs to the authenticated user
        noti = get_object_or_404(api_models.Notification, id=noti_id, user=user)

        noti.seen = True
        noti.save()
        return Response({"message": "Notification marked as seen."}, status=status.HTTP_200_OK)


class DashboardPostCommentAPIView(APIView):
    permission_classes = [IsAuthenticated] # Author replying to comments on their posts
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
        user = request.user # Authenticated user (the author)

        if not all([comment_id, reply]):
            return Response({"message": "Missing comment_id or reply."}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure the comment is on a post owned by the authenticated user
        comment = get_object_or_404(api_models.Comment, id=comment_id, post__user=user)

        comment.reply = reply
        comment.save()

        return Response({"message": "Comment response sent."}, status=status.HTTP_201_CREATED)


class DashboardPostCreateAPIView(generics.CreateAPIView):
    permission_classes = [IsAuthenticated] # Only authenticated users can create posts
    serializer_class = api_serializer.PostSerializer

    def create(self, request, *args, **kwargs):
        # user_id should NOT be sent in the request body; use request.user
        user = request.user 
        title = request.data.get('title')
        image = request.data.get('image')
        description = request.data.get('description')
        tags = request.data.get('tags')
        category_id = request.data.get('category')
        post_status = request.data.get('post_status')

        if not all([title, category_id, post_status]): # user_id removed from required
            return Response({"message": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        # Category is still needed from request data
        category = get_object_or_404(api_models.Category, id=category_id)

        post = api_models.Post.objects.create(
            user=user, # Assign the authenticated user
            title=title,
            image=image,
            description=description,
            tags=tags,
            category=category,
            status=post_status
        )
        # Return serialized post data, not just a message
        serializer = self.get_serializer(post)
        return Response({"message": "Post created successfully.", "post": serializer.data}, status=status.HTTP_201_CREATED)


class DashboardPostEditAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated] # Only authenticated users can edit their own posts
    serializer_class = api_serializer.PostSerializer

    def get_object(self):
        # user_id from URL is redundant here if user must own the post
        post_id = self.kwargs['post_id']
        user = self.request.user # Authenticated user

        # Ensure the post belongs to the authenticated user
        post = get_object_or_404(api_models.Post, user=user, id=post_id)
        return post

    def update(self, request, *args, **kwargs):
        post_instance = self.get_object() # get_object_or_404 handles user/post existence and ownership

        title = request.data.get('title')
        image = request.data.get('image')
        description = request.data.get('description')
        tags = request.data.get('tags')
        category_id = request.data.get('category')
        post_status = request.data.get('post_status')

        if not all([title, category_id, post_status]):
            return Response({"message": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        category = get_object_or_404(api_models.Category, id=category_id)

        post_instance.title = title
        if image != "undefined" and image is not None:
            post_instance.image = image
        post_instance.description = description
        post_instance.tags = tags
        post_instance.category = category
        post_instance.status = post_status
        post_instance.save()
        
        # Return serialized updated post data
        serializer = self.get_serializer(post_instance)
        return Response({"message": "Post updated successfully.", "post": serializer.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        post_instance = self.get_object() # get_object_or_404 handles user/post existence and ownership
        post_instance.delete()
        return Response({"message": "Post deleted successfully."}, status=status.HTTP_204_NO_CONTENT)

# --- Add this new serializer in api/serializer.py ---
# class LikePostResponseSerializer(serializers.Serializer):
#     message = serializers.CharField()
#     liked = serializers.BooleanField()
#     likes_count = serializers.IntegerField()