"""
MongoDB CRUD operations for sites and facilities.
Preserves the exact query patterns from the Node.js Mongoose implementation.
"""
from __future__ import annotations

import logging
import math
import secrets
import string
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_oid(value: str) -> Optional[ObjectId]:
    """Convert a string to ObjectId, return None if invalid."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def _is_object_id(value: str) -> bool:
    """Check if string is a valid 24-char hex ObjectId."""
    try:
        ObjectId(value)
        return len(value) == 24
    except Exception:
        return False


def _random_str(n: int) -> str:
    # secrets over random: these become business identifiers; CSPRNG costs
    # nothing here and keeps them unguessable.
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(n))


def _generate_facility_id(facility_type: str, name: str) -> str:
    """Mirrors generateFacilityCode() from facility.model.js."""
    type_prefix = facility_type[:4].upper()
    name_prefix = name[:4].upper()
    rand = _random_str(4)
    return f"{type_prefix}-{name_prefix}-{rand}"


def _generate_site_id() -> str:
    """Mirrors the pre-save siteId generation in Site.js."""
    ts = int(time.time() * 1000)
    rand = _random_str(6)
    return f"SITE-{ts}-{rand}"


def _format_facility_id(facility_id: str) -> str:
    """Mirrors formatFacilityId() from facility.model.js."""
    return facility_id.replace(' ', '').upper()


def _serialize_doc(doc: Dict) -> Dict:
    """Recursively convert ObjectIds to strings for JSON serialization."""
    if doc is None:
        return None
    result = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = _serialize_doc(v)
        elif isinstance(v, list):
            result[k] = [_serialize_doc(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
        else:
            result[k] = v
    return result


def _transform_site(site: Dict) -> Dict:
    """
    Mirrors transformSite() from site.controller.js.
    Produces the exact same response shape.
    """
    if site is None:
        return None
    s = _serialize_doc(site)

    study = s.get('study')
    if study and isinstance(study, dict):
        study = {
            '_id': study.get('_id') or study.get('id'),
            'studyId': study.get('studyId'),
            'title': study.get('title'),
            'protocolNumber': study.get('protocolNumber'),
            'phase': study.get('phase'),
            'status': study.get('status'),
        }

    facility = s.get('facility')
    if facility and isinstance(facility, dict):
        facility = {
            '_id': facility.get('_id'),
            'facilityId': facility.get('facilityId'),
            'name': facility.get('name'),
            'facilityType': facility.get('facilityType'),
            'address': facility.get('address'),
            'department': facility.get('department'),
        }

    pi = s.get('principalInvestigator')
    if pi and isinstance(pi, dict):
        pi = {
            '_id': pi.get('_id'),
            'userId': pi.get('userId'),
            'firstName': pi.get('firstName'),
            'lastName': pi.get('lastName'),
            'email': pi.get('email'),
            'role': pi.get('role'),
            'phoneNumber': pi.get('phoneNumber'),
        }
    elif pi and isinstance(pi, str):
        pi = None  # not yet populated

    personnel_list = []
    for p in (s.get('sitePersonnel') or []):
        user = p.get('user')
        if isinstance(user, str):
            user = None  # unpopulated ref
        personnel_list.append({
            '_id': p.get('_id'),
            'user': user,
            'role': p.get('role'),
            'assignedAt': p.get('assignedAt'),
            'isActive': p.get('isActive', True),
        })

    audit_trail = []
    for a in (s.get('auditTrail') or []):
        entry = dict(a)
        if entry.get('timestamp') and not isinstance(entry['timestamp'], str):
            entry['timestamp'] = str(entry['timestamp'])
        audit_trail.append(entry)

    return {
        '_id': s.get('_id'),
        'siteId': s.get('siteId'),
        'siteCode': s.get('siteCode'),
        'study': study,
        'facility': facility,
        'principalInvestigator': pi,
        'status': s.get('status'),
        'sitePersonnel': personnel_list,
        'regulatoryApprovals': s.get('regulatoryApprovals') or [],
        'siteDocuments': s.get('siteDocuments') or [],
        'monitoring': s.get('monitoring') or {},
        'qualityMetrics': s.get('qualityMetrics') or {},
        'notifications': s.get('notifications') or [],
        'auditTrail': audit_trail,
        'metadata': s.get('metadata') or {},
        'createdAt': s.get('createdAt'),
        'updatedAt': s.get('updatedAt'),
        'createdBy': s.get('createdBy'),
        'updatedBy': s.get('updatedBy'),
    }


# ─── Facility repository ──────────────────────────────────────────────────────

async def facility_get_all(
    db: AsyncIOMotorDatabase,
    page: int = 1,
    limit: int = 20,
    search: str = '',
    site_type: str = '',
    status: str = '',
    country: str = '',
    sort_by: str = 'createdAt',
    sort_order: str = 'desc',
) -> Dict:
    """Mirrors getAllFacilities() from facility.controller.js."""
    flt: Dict[str, Any] = {}

    if search:
        flt['$or'] = [
            {'name': {'$regex': search, '$options': 'i'}},
            {'facilityId': {'$regex': search, '$options': 'i'}},
            {'campusName': {'$regex': search, '$options': 'i'}},
            {'address.street': {'$regex': search, '$options': 'i'}},
            {'address.city': {'$regex': search, '$options': 'i'}},
            {'address.state': {'$regex': search, '$options': 'i'}},
            {'address.country': {'$regex': search, '$options': 'i'}},
            {'address.postalCode': {'$regex': search, '$options': 'i'}},
        ]
    if site_type:
        flt['facilityType'] = site_type
    if status:
        flt['status'] = status
    if country:
        flt['address.country'] = country

    skip = (page - 1) * limit
    sort_dir = 1 if sort_order == 'asc' else -1

    coll = db['facilities']
    total, docs = await _parallel_count_find(
        coll, flt, sort_by, sort_dir, skip, limit
    )

    serialized = [_serialize_doc(d) for d in docs]
    return {
        'status': 'success',
        'results': len(serialized),
        'total': total,
        'page': page,
        'limit': limit,
        'pages': math.ceil(total / limit) if limit else 0,
        'data': serialized,
    }


async def _parallel_count_find(coll, flt, sort_by, sort_dir, skip, limit):
    import asyncio
    total_coro = coll.count_documents(flt)
    cursor = coll.find(flt).sort(sort_by, sort_dir).skip(skip).limit(limit)
    docs_coro = cursor.to_list(length=limit)
    total, docs = await asyncio.gather(total_coro, docs_coro)
    return total, docs


async def facility_get_one(db: AsyncIOMotorDatabase, facility_id: str) -> Optional[Dict]:
    """Mirrors getFacility() from facility.controller.js."""
    oid = _to_oid(facility_id)
    if oid is None:
        return None
    doc = await db['facilities'].find_one({'_id': oid})
    return _serialize_doc(doc) if doc else None


async def facility_create(db: AsyncIOMotorDatabase, data: Dict) -> Dict:
    """
    Mirrors createFacility() from facility.controller.js.
    Applies facilityType uppercase + facilityId generation (from pre-save middleware).
    """
    now = datetime.now(timezone.utc)

    if data.get('facilityType'):
        data['facilityType'] = data['facilityType'].upper()

    if not data.get('facilityId') and data.get('facilityType') and data.get('name'):
        data['facilityId'] = _generate_facility_id(data['facilityType'], data['name'])

    if data.get('facilityId'):
        data['facilityId'] = _format_facility_id(data['facilityId'])

    data['createdAt'] = now
    data['updatedAt'] = now

    result = await db['facilities'].insert_one(data)
    created = await db['facilities'].find_one({'_id': result.inserted_id})
    return _serialize_doc(created)


async def facility_update(db: AsyncIOMotorDatabase, facility_id: str, data: Dict) -> Optional[Dict]:
    """
    Mirrors updateFacility() from facility.controller.js.
    facilityId is removed from update (pre-findOneAndUpdate middleware behavior).
    """
    oid = _to_oid(facility_id)
    if oid is None:
        return None

    data.pop('facilityId', None)  # mirrors pre-findOneAndUpdate: delete update.facilityId

    if data.get('facilityType'):
        data['facilityType'] = data['facilityType'].upper()

    data['updatedAt'] = datetime.now(timezone.utc)

    doc = await db['facilities'].find_one_and_update(
        {'_id': oid},
        {'$set': data},
        return_document=True,
    )
    return _serialize_doc(doc) if doc else None


async def facility_delete(db: AsyncIOMotorDatabase, facility_id: str) -> bool:
    """Mirrors deleteFacility() from facility.controller.js."""
    oid = _to_oid(facility_id)
    if oid is None:
        return False
    result = await db['facilities'].find_one_and_delete({'_id': oid})
    return result is not None


# ─── Site repository ──────────────────────────────────────────────────────────

async def site_get_all(
    db: AsyncIOMotorDatabase,
    page: int = 1,
    limit: int = 10,
    search: str = '',
    study: str = '',
    facility: str = '',
    status: str = '',
    principal_investigator: str = '',
) -> Dict:
    """
    Mirrors getAllSites() from site.controller.js.
    Uses aggregation pipeline with $lookup for study and facility.
    principalInvestigator population is best-effort (no platformUsersDB).
    """
    flt: Dict[str, Any] = {}

    if search:
        flt['$or'] = [
            {'siteCode': {'$regex': search, '$options': 'i'}},
            {'study.title': {'$regex': search, '$options': 'i'}},
            {'facility.name': {'$regex': search, '$options': 'i'}},
            {'principalInvestigator.firstName': {'$regex': search, '$options': 'i'}},
            {'principalInvestigator.lastName': {'$regex': search, '$options': 'i'}},
        ]
    if study:
        oid = _to_oid(study)
        flt['study'] = oid if oid else study
    if facility:
        oid = _to_oid(facility)
        flt['facility'] = oid if oid else facility
    if status:
        flt['status'] = status
    if principal_investigator:
        oid = _to_oid(principal_investigator)
        flt['principalInvestigator'] = oid if oid else principal_investigator

    skip = (page - 1) * limit

    pipeline = [
        {'$match': flt},
        {'$lookup': {
            'from': 'studies',
            'localField': 'study',
            'foreignField': '_id',
            'as': 'study',
        }},
        {'$lookup': {
            'from': 'facilities',
            'localField': 'facility',
            'foreignField': '_id',
            'as': 'facility',
        }},
        {'$addFields': {
            'study': {'$arrayElemAt': ['$study', 0]},
            'facility': {'$arrayElemAt': ['$facility', 0]},
        }},
        {'$sort': {'createdAt': -1}},
        {'$skip': skip},
        {'$limit': limit},
    ]

    import asyncio
    coll = db['sites']
    sites_coro = coll.aggregate(pipeline).to_list(length=limit)
    total_coro = coll.count_documents(flt)
    sites, total = await asyncio.gather(sites_coro, total_coro)

    # principalInvestigator: best-effort lookup from users collection
    pi_ids = []
    for s in sites:
        if s.get('principalInvestigator') and isinstance(s['principalInvestigator'], ObjectId):
            pi_ids.append(s['principalInvestigator'])
    user_map = await _build_user_map(db, pi_ids)

    serialized = []
    for s in sites:
        pi_oid = s.get('principalInvestigator')
        pi_data = user_map.get(str(pi_oid)) if pi_oid else None
        s['principalInvestigator'] = pi_data

        personnel = []
        for p in (s.get('sitePersonnel') or []):
            u_oid = p.get('user')
            u_data = user_map.get(str(u_oid)) if u_oid else None
            personnel.append({
                '_id': str(p['_id']) if p.get('_id') else None,
                'user': u_data,
                'role': p.get('role'),
                'assignedAt': p.get('assignedAt'),
                'isActive': p.get('isActive', True),
            })
        s['sitePersonnel'] = personnel
        serialized.append(_transform_site(s))

    return {
        'success': True,
        'data': serialized,
        'pagination': {
            'page': page,
            'limit': limit,
            'total': total,
            'pages': math.ceil(total / limit) if limit else 0,
        },
    }


async def _build_user_map(db: AsyncIOMotorDatabase, oids: List[ObjectId]) -> Dict[str, Any]:
    """Fetch users from local users collection by ObjectId list."""
    if not oids:
        return {}
    try:
        users = await db['users'].find({'_id': {'$in': oids}}).to_list(length=len(oids))
        result = {}
        for u in users:
            uid = str(u['_id'])
            result[uid] = {
                '_id': uid,
                'userId': u.get('userId') or uid,
                'firstName': u.get('firstName'),
                'lastName': u.get('lastName'),
                'email': u.get('email'),
                'role': u.get('role') or u.get('globalRole') or 'USER',
                'phoneNumber': u.get('phoneNumber') or '',
            }
        return result
    except Exception as exc:
        logger.warning(f"[site_creation] User map lookup failed: {exc}")
        return {}


async def site_get_one(db: AsyncIOMotorDatabase, site_id: str) -> Optional[Dict]:
    """Mirrors getSite() from site.controller.js."""
    oid = _to_oid(site_id)
    if oid is None:
        return None

    site = await db['sites'].find_one({'_id': oid})
    if not site:
        return None

    # Populate study and facility
    study_oid = site.get('study')
    facility_oid = site.get('facility')
    pi_oid = site.get('principalInvestigator')

    import asyncio
    study_coro = db['studies'].find_one({'_id': study_oid}) if study_oid else _noop()
    facility_coro = db['facilities'].find_one({'_id': facility_oid}) if facility_oid else _noop()
    study, facility = await asyncio.gather(study_coro, facility_coro)

    site['study'] = study
    site['facility'] = facility

    # Populate principal investigator
    pi_ids = [pi_oid] if pi_oid else []
    for p in (site.get('sitePersonnel') or []):
        u_oid = p.get('user')
        if u_oid and isinstance(u_oid, ObjectId):
            pi_ids.append(u_oid)

    user_map = await _build_user_map(db, pi_ids)
    site['principalInvestigator'] = user_map.get(str(pi_oid)) if pi_oid else None

    personnel = []
    for p in (site.get('sitePersonnel') or []):
        u_oid = p.get('user')
        u_data = user_map.get(str(u_oid)) if u_oid else None
        personnel.append({**p, 'user': u_data})
    site['sitePersonnel'] = personnel

    return _transform_site(site)


async def _noop():
    return None


async def site_create(db: AsyncIOMotorDatabase, data: Dict, request_ip: str = '', user_agent: str = '') -> Dict:
    """
    Mirrors createSite() from site.controller.js.
    Resolves study by ObjectId or studyId string.
    Generates siteCode and siteId if not provided.
    """
    now = datetime.now(timezone.utc)

    # Resolve study — tries MongoDB first, falls back to storing the raw value
    # (studies may live in PostgreSQL and be referenced by UUID string)
    study_val = data.get('study')
    if study_val:
        is_oid = _is_object_id(study_val)
        if is_oid:
            study = await db['studies'].find_one({'_id': ObjectId(study_val)})
        else:
            study = await db['studies'].find_one({'studyId': study_val})
        if study:
            data['study'] = study['_id']  # store as ObjectId when found in Mongo
        # else: keep study_val as-is (PostgreSQL UUID or external reference)

    # Generate siteCode
    if not data.get('siteCode') and data.get('study'):
        study_doc = await db['studies'].find_one({'_id': data['study']})
        facility_doc = await db['facilities'].find_one({'_id': _to_oid(str(data.get('facility', '')))}) if data.get('facility') else None
        pi_doc = await db['users'].find_one({'_id': _to_oid(str(data.get('principalInvestigator', '')))}) if data.get('principalInvestigator') else None

        study_id_str = str(study_doc.get('studyId', '')) if study_doc else ''
        study_code = study_id_str[-3:] if len(study_id_str) >= 3 else 'STD'
        fac_id_str = str(facility_doc.get('facilityId', '')) if facility_doc else ''
        fac_code = fac_id_str[-3:] if len(fac_id_str) >= 3 else 'FAC'
        pi_uid_str = str(pi_doc.get('userId', '')) if pi_doc else ''
        pi_code = pi_uid_str[-3:] if len(pi_uid_str) >= 3 else 'PI'
        data['siteCode'] = f"SITE-{study_code}-{fac_code}-{pi_code}"

    if not data.get('siteCode'):
        ts = str(int(time.time() * 1000))[-6:]
        data['siteCode'] = f"SITE-{ts}-{_random_str(4)}"

    # Generate siteId
    if not data.get('siteId'):
        data['siteId'] = _generate_site_id()

    # Convert facility and principalInvestigator strings to ObjectId
    if data.get('facility') and isinstance(data['facility'], str):
        oid = _to_oid(data['facility'])
        if oid:
            data['facility'] = oid
    if data.get('principalInvestigator') and isinstance(data['principalInvestigator'], str):
        oid = _to_oid(data['principalInvestigator'])
        if oid:
            data['principalInvestigator'] = oid

    # Convert sitePersonnel user refs
    for p in (data.get('sitePersonnel') or []):
        if p.get('user') and isinstance(p['user'], str):
            oid = _to_oid(p['user'])
            if oid:
                p['user'] = oid

    # createdBy: best-effort default
    if not data.get('createdBy'):
        admin = await db['users'].find_one({'role': 'ADMIN'})
        data['createdBy'] = admin['_id'] if admin else ObjectId()

    data['createdAt'] = now
    data['updatedAt'] = now

    # Audit trail entry
    audit_entry = {
        '_id': ObjectId(),
        'action': 'CREATE',
        'timestamp': now,
        'user': data['createdBy'],
        'details': {'action': 'Site created'},
        'ipAddress': request_ip,
        'userAgent': user_agent,
    }
    data.setdefault('auditTrail', []).append(audit_entry)

    result = await db['sites'].insert_one(data)

    # Return populated site
    return await site_get_one(db, str(result.inserted_id))


async def site_update(db: AsyncIOMotorDatabase, site_id: str, data: Dict) -> Optional[Dict]:
    """
    Mirrors updateSite() from site.controller.js.
    Normalizes ObjectId fields. Resolves study by studyId string if needed.
    """
    oid = _to_oid(site_id)
    if oid is None:
        return None

    # Normalize study
    if 'study' in data and data['study'] is not None:
        sv = data['study']
        if isinstance(sv, dict):
            data['study'] = _to_oid(str(sv.get('_id') or sv.get('id', '')))
        elif isinstance(sv, str):
            if not _is_object_id(sv):
                study = await db['studies'].find_one({'studyId': sv})
                if study:
                    data['study'] = study['_id']
                # else: keep as-is (PostgreSQL UUID or external reference)
            else:
                data['study'] = ObjectId(sv)

    # Normalize facility
    if 'facility' in data and data['facility'] is not None:
        fv = data['facility']
        if isinstance(fv, dict):
            data['facility'] = _to_oid(str(fv.get('_id') or fv.get('id', '')))
        elif isinstance(fv, str):
            oid2 = _to_oid(fv)
            if oid2:
                data['facility'] = oid2

    # Normalize principalInvestigator
    if 'principalInvestigator' in data and data['principalInvestigator'] is not None:
        piv = data['principalInvestigator']
        if isinstance(piv, dict):
            data['principalInvestigator'] = _to_oid(str(piv.get('_id') or piv.get('id', '')))
        elif isinstance(piv, str):
            oid2 = _to_oid(piv)
            if oid2:
                data['principalInvestigator'] = oid2

    # Normalize sitePersonnel.user
    if data.get('sitePersonnel') and isinstance(data['sitePersonnel'], list):
        normalized = []
        for p in data['sitePersonnel']:
            if isinstance(p.get('user'), dict):
                p = {**p, 'user': _to_oid(str(p['user'].get('_id') or p['user'].get('id', '')))}
            elif isinstance(p.get('user'), str):
                oid2 = _to_oid(p['user'])
                if oid2:
                    p = {**p, 'user': oid2}
            normalized.append(p)
        data['sitePersonnel'] = normalized

    data['updatedAt'] = datetime.now(timezone.utc)

    updated = await db['sites'].find_one_and_update(
        {'_id': oid},
        {'$set': data},
        return_document=True,
    )
    if not updated:
        return None

    return await site_get_one(db, site_id)


async def site_delete(db: AsyncIOMotorDatabase, site_id: str) -> bool:
    """Mirrors deleteSite() from site.controller.js."""
    oid = _to_oid(site_id)
    if oid is None:
        return False
    result = await db['sites'].find_one_and_delete({'_id': oid})
    return result is not None


async def site_add_personnel(db: AsyncIOMotorDatabase, site_id: str, user_id: str, role: str) -> Optional[Dict]:
    """Mirrors addPersonnel() method from Site.js schema."""
    oid = _to_oid(site_id)
    if oid is None:
        return None

    user_oid = _to_oid(user_id)
    personnel_entry = {
        '_id': ObjectId(),
        'user': user_oid or user_id,
        'role': role,
        'assignedAt': datetime.now(timezone.utc),
        'isActive': True,
    }

    await db['sites'].update_one(
        {'_id': oid},
        {'$push': {'sitePersonnel': personnel_entry},
         '$set': {'updatedAt': datetime.now(timezone.utc)}},
    )
    return await site_get_one(db, site_id)


async def site_remove_personnel(db: AsyncIOMotorDatabase, site_id: str, user_id: str) -> Optional[Dict]:
    """Mirrors removePersonnel() method from Site.js schema — sets isActive=false."""
    oid = _to_oid(site_id)
    if oid is None:
        return None

    user_oid = _to_oid(user_id)

    await db['sites'].update_one(
        {'_id': oid, 'sitePersonnel.user': user_oid or user_id},
        {'$set': {
            'sitePersonnel.$.isActive': False,
            'updatedAt': datetime.now(timezone.utc),
        }},
    )
    return await site_get_one(db, site_id)


async def sites_by_study(db: AsyncIOMotorDatabase, study_id: str) -> List[Dict]:
    """
    Mirrors getSitesByStudy() from site.controller.js.
    Accepts ObjectId string or studyId string.
    """
    is_oid = _is_object_id(study_id)
    if is_oid:
        study_oid = ObjectId(study_id)
    else:
        study = await db['studies'].find_one({'studyId': study_id})
        if not study:
            return None  # signals 404 to caller
        study_oid = study['_id']

    sites = await db['sites'].find({'study': study_oid}).to_list(length=1000)

    facility_ids = list({str(s.get('facility')) for s in sites if s.get('facility')})
    pi_ids_raw = [s.get('principalInvestigator') for s in sites if s.get('principalInvestigator')]

    import asyncio
    fac_coro = db['facilities'].find(
        {'_id': {'$in': [_to_oid(f) for f in facility_ids if _to_oid(f)]}}
    ).to_list(length=len(facility_ids)) if facility_ids else _noop_list()

    pi_oids = [x for x in pi_ids_raw if isinstance(x, ObjectId)]
    user_map = await _build_user_map(db, pi_oids)
    facilities_list = await fac_coro

    fac_map = {str(f['_id']): f for f in (facilities_list or [])}

    # Populate study (already know it)
    study_doc = await db['studies'].find_one({'_id': study_oid})

    result = []
    for s in sites:
        s['study'] = study_doc
        s['facility'] = fac_map.get(str(s.get('facility')))
        pi_oid = s.get('principalInvestigator')
        s['principalInvestigator'] = user_map.get(str(pi_oid)) if pi_oid else None
        result.append(_transform_site(s))
    return result


async def _noop_list():
    return []


async def sites_by_facility(db: AsyncIOMotorDatabase, facility_id: str) -> List[Dict]:
    """Mirrors getSitesByFacility() from site.controller.js."""
    fac_oid = _to_oid(facility_id)
    if fac_oid is None:
        return []

    sites = await db['sites'].find({'facility': fac_oid}).to_list(length=1000)

    study_ids = [s.get('study') for s in sites if s.get('study')]
    pi_ids = [s.get('principalInvestigator') for s in sites if s.get('principalInvestigator')]

    study_docs = await db['studies'].find({'_id': {'$in': study_ids}}).to_list(length=len(study_ids)) if study_ids else []
    study_map = {str(s['_id']): s for s in study_docs}

    facility_doc = await db['facilities'].find_one({'_id': fac_oid})

    pi_oids = [x for x in pi_ids if isinstance(x, ObjectId)]
    user_map = await _build_user_map(db, pi_oids)

    result = []
    for s in sites:
        s['study'] = study_map.get(str(s.get('study')))
        s['facility'] = facility_doc
        pi_oid = s.get('principalInvestigator')
        s['principalInvestigator'] = user_map.get(str(pi_oid)) if pi_oid else None
        result.append(_transform_site(s))
    return result


async def sites_by_investigator(db: AsyncIOMotorDatabase, user_id: str) -> List[Dict]:
    """Mirrors getSitesByPrincipalInvestigator() from site.controller.js."""
    user_oid = _to_oid(user_id)
    flt = {'principalInvestigator': user_oid} if user_oid else {'principalInvestigator': user_id}
    sites = await db['sites'].find(flt).to_list(length=1000)

    study_ids = [s.get('study') for s in sites if s.get('study')]
    fac_ids = [s.get('facility') for s in sites if s.get('facility')]

    import asyncio
    study_docs, fac_docs = await asyncio.gather(
        db['studies'].find({'_id': {'$in': study_ids}}).to_list(length=len(study_ids)) if study_ids else _noop_list(),
        db['facilities'].find({'_id': {'$in': fac_ids}}).to_list(length=len(fac_ids)) if fac_ids else _noop_list(),
    )
    study_map = {str(s['_id']): s for s in (study_docs or [])}
    fac_map = {str(f['_id']): f for f in (fac_docs or [])}

    pi_doc = await db['users'].find_one({'_id': user_oid}) if user_oid else None

    result = []
    for s in sites:
        s['study'] = study_map.get(str(s.get('study')))
        s['facility'] = fac_map.get(str(s.get('facility')))
        s['principalInvestigator'] = {
            '_id': str(pi_doc['_id']),
            'userId': pi_doc.get('userId'),
            'firstName': pi_doc.get('firstName'),
            'lastName': pi_doc.get('lastName'),
            'email': pi_doc.get('email'),
            'role': pi_doc.get('role'),
        } if pi_doc else None
        result.append(_transform_site(s))
    return result
