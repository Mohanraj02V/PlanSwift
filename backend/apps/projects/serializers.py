from __future__ import annotations

from rest_framework import serializers

from apps.projects.models import Project, ProjectPage, ProjectVersion


class ProjectVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectVersion
        fields = [
            "id",
            "version_number",
            "source_sha256",
            "deterministic_digest_sha256",
            "is_current",
            "metadata",
            "created_at",
        ]


class ProjectPageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectPage
        fields = [
            "id",
            "native_guid",
            "name",
            "native_class",
            "page_type",
            "order_index",
            "image_property_guid",
            "tiff_archive_path",
            "tiff_size_bytes",
            "scale_units",
            "page_width_raw",
            "page_height_raw",
            "numeric_scale_factor",
            "section_count",
            "provenance",
        ]


class ProjectSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    current_version = serializers.SerializerMethodField()
    object_count = serializers.SerializerMethodField()
    page_count = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "native_guid",
            "description",
            "notes",
            "project_type",
            "measurement_system",
            "excel_workbook_connected",
            "xml_encoding",
            "native_timestamp_raw",
            "current_version",
            "object_count",
            "page_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "organization_name",
            "native_guid",
            "current_version",
            "object_count",
            "page_count",
            "created_at",
            "updated_at",
        ]

    def get_current_version(self, obj: Project):
        ver = obj.versions.filter(is_current=True).first()
        return ProjectVersionSerializer(ver).data if ver else None

    def get_object_count(self, obj: Project) -> int:
        ver = obj.versions.filter(is_current=True).first()
        return ver.project_objects.count() if ver else 0

    def get_page_count(self, obj: Project) -> int:
        ver = obj.versions.filter(is_current=True).first()
        return ver.pages.count() if ver else 0
