import os
import requests
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL', '').rstrip('/')
SUPABASE_KEY = os.getenv('SUPABASE_KEY', '')

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME', ''),
    api_key=os.getenv('CLOUDINARY_API_KEY', ''),
    api_secret=os.getenv('CLOUDINARY_API_SECRET', ''),
    secure=True,
)


def _headers(json_body=False):
    h = {
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    }
    if json_body:
        h['Content-Type'] = 'application/json'
    return h


def save_memory_to_supabase(memory_id, message='', photos=None, videos=None, ready=False):
    r = requests.post(
        f'{SUPABASE_URL}/rest/v1/memories',
        headers={**_headers(True), 'Prefer': 'return=minimal'},
        json={
            'id': memory_id,
            'message': message or '',
            'photos': photos or [],
            'videos': videos or [],
            'status': 'active',
            'ready': bool(ready),
        },
        timeout=30,
    )
    r.raise_for_status()
    return True


def update_memory_in_supabase(memory_id, message=None, photos=None, videos=None, status=None, deleted_at=None, ready=None):
    data = {}
    if message is not None:
        data['message'] = message
    if photos is not None:
        data['photos'] = photos
    if videos is not None:
        data['videos'] = videos
    if status is not None:
        data['status'] = status
    if deleted_at is not None:
        data['deleted_at'] = deleted_at
    if ready is not None:
        data['ready'] = bool(ready)
    if not data:
        return True

    r = requests.patch(
        f'{SUPABASE_URL}/rest/v1/memories',
        headers={**_headers(True), 'Prefer': 'return=minimal'},
        params={'id': f'eq.{memory_id}'},
        json=data,
        timeout=30,
    )
    r.raise_for_status()
    return True


def get_memory_from_supabase(memory_id):
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/memories',
        headers=_headers(),
        params={'id': f'eq.{memory_id}', 'select': '*'},
        timeout=30,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def list_memories_from_supabase(include_trash=True):
    params = {'select': '*', 'order': 'created_at.desc'}
    if not include_trash:
        params['status'] = 'eq.active'
    r = requests.get(
        f'{SUPABASE_URL}/rest/v1/memories',
        headers=_headers(),
        params=params,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def upload_to_cloudinary(file_obj, resource_type='auto'):
    result = cloudinary.uploader.upload(
        file_obj,
        resource_type=resource_type,
        folder='memoryqr',
    )
    return {
        'url': result['secure_url'],
        'public_id': result.get('public_id', ''),
        'resource_type': result.get('resource_type', resource_type),
        'format': result.get('format', ''),
        'bytes': result.get('bytes', 0),
    }


def delete_cloudinary_asset(public_id, resource_type='image'):
    if not public_id:
        return False
    cloudinary.uploader.destroy(public_id, resource_type=resource_type, invalidate=True)
    return True
