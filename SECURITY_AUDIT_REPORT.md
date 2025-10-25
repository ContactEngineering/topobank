# Security Audit Report: Topobank Application

**Date:** 2025-10-25
**Auditor:** Claude (AI Security Analyst)
**Scope:** Identification of potential security risks leading to unauthorized data access

---

## Executive Summary

This security audit identified **10 categories of vulnerabilities** that could lead to data leaking to unauthorized users. The most critical issues involve **information disclosure through object enumeration**, **insufficient permission checks**, and **exposure of sensitive metadata**. While the application has a robust permission system in place, several implementation gaps could allow attackers to extract information about resources they shouldn't have access to.

**Risk Level Distribution:**
- **CRITICAL**: 3 vulnerabilities
- **HIGH**: 4 vulnerabilities
- **MEDIUM**: 2 vulnerabilities
- **LOW**: 1 vulnerability

---

## Critical Vulnerabilities

### 1. Object Existence Enumeration via Error Responses [CRITICAL]

**Risk:** Attackers can enumerate valid object IDs even without permission to access them.

**Technical Details:**
Multiple API endpoints use `Model.objects.get(pk=pk)` instead of `get_object_or_404()`. When an object doesn't exist, Django raises `DoesNotExist` exception (typically resulting in 500 error), whereas permission checks return 403/404. This difference allows attackers to distinguish between "object doesn't exist" and "object exists but you don't have permission".

**Affected Locations:**

1. **topobank/manager/v1/views.py:313** - `force_inspect()` endpoint
   ```python
   instance = Topography.objects.get(pk=pk)
   # Permission check happens AFTER retrieval
   ```

2. **topobank/manager/v1/views.py:334** - `set_surface_permissions()` endpoint
   ```python
   obj = Surface.objects.get(pk=pk)
   # Permission check happens AFTER retrieval
   ```

3. **topobank/authorization/views.py** - Lines 46, 71, 81, 106
   ```python
   permission_set = PermissionSet.objects.get(pk=pk)
   # Authorization check happens AFTER retrieval
   ```

4. **topobank/manager/v2/views.py:118** - `upload_zip_finish()` endpoint
   ```python
   zip_container = ZipContainer.objects.get(pk=pk)
   ```

5. **topobank/organizations/views.py:41** - `get_user_and_organization()`
   ```python
   organization = Organization.objects.get(pk=pk)
   ```

6. **topobank/users/views.py:50** - `get_user_and_organization()`
   ```python
   user = User.objects.get(pk=pk)
   ```

**Attack Scenario:**
```python
# Attacker script to enumerate valid Surface IDs
for surface_id in range(1, 10000):
    response = requests.patch(f"/api/surface/{surface_id}/permissions/")
    if response.status_code == 403:  # Object exists, permission denied
        print(f"Valid Surface ID: {surface_id}")
    elif response.status_code == 500:  # DoesNotExist
        continue
```

**Impact:**
- Database ID enumeration
- Information about data volume
- Potential timing attacks to determine creation patterns
- Reconnaissance for targeted attacks

**Recommendation:**
Replace all `Model.objects.get(pk=pk)` calls with `get_object_or_404(Model, pk=pk)` to ensure consistent 404 responses. The authorization check using `authorize_user()` will then raise `NotFound` (404) for objects the user has no access to, preventing enumeration.

---

### 2. Global Statistics Disclosure [CRITICAL]

**Risk:** Sensitive database statistics exposed to unauthenticated users.

**Location:** topobank/manager/v1/views.py:476-495

**Code:**
```python
@api_view(["GET"])
def statistics(request):
    # Global statistics
    stats = {
        "nb_users": User.objects.count() - 1,  # -1 because we don't count the anonymous user
        "nb_surfaces": Surface.objects.count(),
        "nb_topographies": Topography.objects.count(),
    }
    # More stats for authenticated users...
    return Response(stats)
```

**Issues:**
1. **No authentication required** - Any visitor can access this endpoint
2. Exposes total user count (competitive intelligence)
3. Exposes total dataset count (database size inference)
4. Can be used for timing attacks (monitor growth patterns)

**Impact:**
- Competitive intelligence gathering
- Database capacity estimation for DoS attack planning
- User growth tracking
- Research activity monitoring

**Recommendation:**
1. Require authentication: Add `@permission_classes([IsAuthenticated])`
2. Consider removing global statistics entirely or limiting to staff users
3. Implement rate limiting on this endpoint

---

### 3. Memory Usage Endpoint Without Authentication [CRITICAL]

**Risk:** Internal system metrics exposed without authentication.

**Location:** topobank/manager/v1/views.py:498-507

**Code:**
```python
@api_view(["GET"])
def memory_usage(request):
    r = Topography.objects.values(
        "resolution_x", "resolution_y", "task_memory"
    ).annotate(
        task_duration=F("task_end_time") - F("task_start_time"),
        nb_data_pts=F("resolution_x") * Case(When(resolution_y__isnull=False, then=F("resolution_y")), default=1),
    )
    return Response(list(r))
```

**Issues:**
1. **No authentication or permission checks**
2. Exposes memory usage patterns for ALL topographies
3. Exposes processing time for different data sizes
4. Reveals system capacity and performance characteristics

**Impact:**
- DoS attack planning (identify memory-intensive operations)
- System capacity estimation
- Timing attack reconnaissance
- Performance profiling of backend infrastructure

**Recommendation:**
1. **Remove this endpoint from production** or restrict to staff only
2. If needed for monitoring, move to admin-only interface
3. Add authentication: `@permission_classes([IsAdminUser])`

---

## High Severity Vulnerabilities

### 4. Permission List Disclosure in Serializers [HIGH]

**Risk:** Users can see complete list of who has access to shared resources.

**Locations:**
- topobank/manager/v1/serializers.py:214-231 (TopographySerializer)
- topobank/manager/v1/serializers.py:331-348 (SurfaceSerializer)

**Code:**
```python
def get_permissions(self, obj: Topography) -> dict:
    request = self.context["request"]
    current_user = request.user
    user_permissions = obj.permissions.user_permissions.all()
    return {
        "current_user": {
            "user": current_user.get_absolute_url(request),
            "permission": obj.get_permission(current_user),
        },
        "other_users": [
            {
                "user": perm.user.get_absolute_url(request),
                "permission": perm.allow,
            }
            for perm in user_permissions
            if perm.user != current_user
        ],
    }
```

**Issues:**
1. Exposes ALL users with access to a resource
2. Exposes their permission levels (view/edit/full)
3. No business need for users with "view" permission to see who else has access
4. Reveals collaboration patterns and organizational structure

**Impact:**
- Social engineering attacks (knowing who has full access)
- Insider threat intelligence
- Privacy violation (users may not want others to know they have access)
- Organizational structure mapping

**Recommendation:**
1. **Restrict permission list visibility**:
   - Only show `other_users` to users with "full" permission
   - Regular users should only see their own permission
2. Alternative: Only show count of other users, not identities

**Proposed Fix:**
```python
def get_permissions(self, obj: Topography) -> dict:
    request = self.context["request"]
    current_user = request.user
    user_permission = obj.get_permission(current_user)

    result = {
        "current_user": {
            "user": current_user.get_absolute_url(request),
            "permission": user_permission,
        }
    }

    # Only show other users if current user has "full" permission
    if user_permission == "full":
        user_permissions = obj.permissions.user_permissions.all()
        result["other_users"] = [
            {
                "user": perm.user.get_absolute_url(request),
                "permission": perm.allow,
            }
            for perm in user_permissions
            if perm.user != current_user
        ]

    return result
```

---

### 5. User Email Address Exposure [HIGH]

**Risk:** Email addresses exposed to any authenticated user in same organization.

**Location:** topobank/users/serializers.py:13-28

**Code:**
```python
class UserSerializer(StrictFieldMixin, serializers.HyperlinkedModelSerializer):
    class Meta:
        model = User
        fields = [
            "url", "id", "api",
            "name", "username", "orcid",
            "email",  # EXPOSED
            "date_joined", "is_verified",
        ]
```

**Access Control:** topobank/users/views.py:19-46
```python
def get_queryset(self):
    # Non-staff users can see users in their organizations
    if not self.request.user.is_staff:
        qs = qs.filter(
            Q(id=self.request.user.id)
            | Q(groups__in=self.request.user.groups.all())
        )
    return qs
```

**Issues:**
1. Email addresses visible to ALL organization members
2. No legitimate business need for peer-to-peer email visibility
3. Can be used for:
   - Phishing attacks
   - Social engineering
   - Spam targeting
   - Impersonation attacks

**Impact:**
- Phishing attack surface
- Privacy violation
- GDPR compliance concerns
- Social engineering risks

**Recommendation:**
1. **Remove email from UserSerializer fields** entirely
2. If email visibility is required:
   - Only show email to staff users
   - Or implement per-user privacy settings
3. Add email to `read_only_fields` if kept

---

### 6. Organization Membership Enumeration [HIGH]

**Risk:** Combined with email exposure, allows mapping of organizational structure.

**Location:** topobank/users/views.py:19-46

**Code:**
```python
def get_queryset(self):
    # Non-staff users can see users in their organizations
    if not self.request.user.is_staff:
        qs = qs.filter(
            Q(id=self.request.user.id)
            | Q(groups__in=self.request.user.groups.all())
        )
    # Filter for organization
    if organization is not None:
        qs = qs.filter(groups__organization=organization)
    return qs
```

**Issues:**
1. Any org member can list all other members
2. Combined with email exposure (#5), creates complete directory
3. Can be filtered by organization parameter
4. No rate limiting on user enumeration

**Attack Scenario:**
```python
# List all users in organization
response = requests.get("/api/users/v1/user/?organization=5")
# Returns: names, emails, ORCID IDs, join dates for all members
```

**Impact:**
- Complete organizational directory creation
- Targeted phishing campaigns
- Competitive intelligence
- Social engineering preparation

**Recommendation:**
1. Implement privacy controls for user visibility
2. Remove email from serializer (see #5)
3. Consider requiring explicit "colleague" relationships before visibility
4. Add rate limiting to user listing endpoints

---

### 7. Tag Permission Bypass Potential [HIGH]

**Risk:** Tag permission endpoint lacks complete authorization validation.

**Location:** topobank/manager/v1/views.py:382-434 - `set_tag_permissions()`

**Code:**
```python
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def set_tag_permissions(request, name=None):
    logged_in_user = request.user
    obj = Tag.objects.get(name=name)  # ❌ Uses .get() not get_object_or_404

    # ... validation ...

    # Loop over all surfaces
    obj.authorize_user(logged_in_user)  # ✅ Authorization happens here
    for surface in obj.get_descendant_surfaces():
        # Check that user has the right to modify permissions
        if surface.has_permission(logged_in_user, "full"):
            # ... grant permissions ...
```

**Issues:**
1. Uses `Tag.objects.get(name=name)` - enables object existence enumeration
2. Tag authorization check could raise exception AFTER object retrieval
3. Complex multi-object permission logic increases attack surface
4. Line 423: Bug - should be `surface.revoke_permission(organization)` not `obj.revoke_permission(organization)`

**Impact:**
- Tag name enumeration
- Inconsistent error responses reveal data existence
- Potential permission bypass through complex logic

**Recommendation:**
1. Use `get_object_or_404(Tag, name=name)`
2. Fix line 423 bug
3. Add comprehensive tests for permission edge cases

---

## Medium Severity Vulnerabilities

### 8. Download Surface Permission Check Timing [MEDIUM]

**Risk:** Permission checks occur after object retrieval, enabling timing attacks.

**Location:** topobank/manager/v1/views.py:282-294

**Code:**
```python
@api_view(["GET"])
def download_surface(request, surface_ids):
    # Parse IDs
    surface_ids = [int(surface_id) for surface_id in surface_ids.split(",")]

    # Get surfaces from database
    surfaces = [get_object_or_404(Surface, id=surface_id) for surface_id in surface_ids]

    # Trigger the actual download
    return download_surfaces(request, surfaces)  # Permission check is inside here
```

**Issues:**
1. Multiple database queries before permission check
2. Timing difference between "exists" and "no permission"
3. Could leak information about object existence through timing

**Impact:**
- Timing-based object enumeration
- Limited practical exploitability
- Could reveal database query patterns

**Recommendation:**
1. Move permission check before object retrieval
2. Use queryset filtering: `Surface.objects.for_user(request.user).filter(id__in=surface_ids)`

---

### 9. Anonymous User Data Access [MEDIUM]

**Risk:** Anonymous user permission system could leak published data unintentionally.

**Locations:**
- topobank/users/anonymous.py - Anonymous user definition
- topobank/authorization/models.py:283-289 - Anonymous user in queries

**Code:**
```python
def for_user(self, user: User, permission: ViewEditFull = "view") -> QuerySet:
    if permission == "view":
        return self.get_queryset().filter(
            # If anonymous has access, anybody can access
            Q(permissions__user_permissions__user=get_anonymous_user())
            | Q(permissions__user_permissions__user=user)
            | Q(permissions__organization_permissions__organization__group__in=user.groups.all())
        )
```

**Issues:**
1. Data with anonymous user permission is accessible to everyone
2. Need to verify published surfaces properly clear permissions
3. Potential for misconfigured permissions to leak private data

**Impact:**
- Unintentional public data exposure
- Published dataset permission management risks
- Configuration errors could expose private data

**Recommendation:**
1. Add automated tests verifying:
   - Published datasets have correct anonymous access
   - Unpublished datasets never have anonymous access
2. Add migration to audit existing permissions
3. Consider separate "public" flag instead of anonymous user permissions

---

## Low Severity Vulnerabilities

### 10. Add/Remove Organization Permission Check [LOW]

**Risk:** Permission checks on organization add/remove endpoints use class-level, not object-level permissions.

**Locations:**
- topobank/organizations/views.py:40-60
- topobank/users/views.py:56-69

**Code:**
```python
@api_view(["POST"])
@permission_classes([OrganizationPermission])  # ❌ Class-level permission
def add_user(request, pk: int):
    user, organization = get_user_and_organization(request, pk)
    user.groups.add(organization.group)
    return Response({})
```

**Issues:**
1. `@permission_classes` decorator applies `has_permission()` not `has_object_permission()`
2. Object retrieval in `get_user_and_organization()` happens without object-level check
3. DRF should call `has_object_permission()` but unclear if it does for `@api_view`

**Impact:**
- Potentially allows unauthorized organization membership changes
- Depends on DRF's internal handling of permission checks for function views

**Recommendation:**
1. Add explicit object-level permission check:
```python
@api_view(["POST"])
@permission_classes([OrganizationPermission])
def add_user(request, pk: int):
    organization = get_object_or_404(Organization, pk=pk)
    # Explicit object permission check
    permission = OrganizationPermission()
    if not permission.has_object_permission(request, None, organization):
        return HttpResponseForbidden()

    user = resolve_user(request.data.get("user"))
    user.groups.add(organization.group)
    return Response({})
```

---

## Additional Security Observations

### Positive Security Patterns

The codebase demonstrates several strong security practices:

1. **Comprehensive Permission System**: Well-designed hierarchical permissions (view/edit/full)
2. **Queryset Filtering**: `AuthorizedManager.for_user()` properly filters querysets
3. **Permission Mixins**: Consistent use of `PermissionMixin` across models
4. **404 for Unauthorized**: `authorize_user()` raises `NotFound` to prevent info disclosure
5. **CSRF Protection**: Properly configured in settings
6. **SSL/HTTPS Enforcement**: Production settings enforce secure connections
7. **Atomic Transactions**: Database operations use atomic requests

### Recommendations for Defense in Depth

1. **Rate Limiting**: Implement rate limiting on all API endpoints, especially:
   - User listing
   - Statistics
   - Download endpoints

2. **Audit Logging**: Add audit logging for:
   - Permission changes
   - Failed authorization attempts
   - Bulk data access (downloads)

3. **API Documentation Security**: Review OpenAPI schema exposure via `/api/schema/swagger-ui/`
   - Ensure sensitive endpoints aren't documented publicly
   - Consider authentication requirement for API documentation

4. **Input Validation**: Add stricter validation on:
   - CSV ID parsing in download endpoints
   - Tag name patterns
   - Organization/user resolution

5. **Security Headers**: Verify all security headers are properly set:
   - Content-Security-Policy
   - X-Content-Type-Options
   - X-Frame-Options (already set to DENY ✓)

---

## Remediation Priority

### Immediate Action Required (Critical)
1. Fix object enumeration vulnerabilities (#1)
2. Add authentication to statistics endpoint (#2)
3. Remove/restrict memory_usage endpoint (#3)

### High Priority (This Sprint)
4. Restrict permission list visibility (#4)
5. Remove email from user serializer (#5)
6. Fix tag permission bugs (#7)

### Medium Priority (Next Sprint)
8. Refactor download permission checks (#8)
9. Audit anonymous user permissions (#9)

### Low Priority (Backlog)
10. Explicit object-level checks for org endpoints (#10)
6. Review organization enumeration policies (#6)

---

## Testing Recommendations

Create test cases for:
1. Object enumeration attempts with invalid IDs
2. Unauthorized access to permission lists
3. Cross-organization data access attempts
4. Anonymous user permission edge cases
5. Permission escalation attempts
6. Concurrent permission modifications

---

## Compliance Considerations

### GDPR Implications
- Email exposure may violate data minimization principles
- User enumeration could be considered profiling
- Recommend privacy impact assessment for user data exposure

### Data Protection
- Implement data access logging
- Consider user consent for visibility in organization directories
- Document data sharing policies clearly

---

## Conclusion

The Topobank application has a solid foundation with a well-designed permission system. However, several implementation gaps create opportunities for information disclosure. The most critical issues involve object enumeration through error responses and exposure of sensitive metadata without proper authorization.

**Estimated Remediation Effort:**
- Critical issues: 2-3 developer days
- High priority: 3-5 developer days
- Medium priority: 2-3 developer days
- Total: ~8-11 developer days

All identified vulnerabilities are fixable through code changes without requiring architectural modifications.
