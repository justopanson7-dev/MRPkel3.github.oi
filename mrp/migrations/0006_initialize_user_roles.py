from django.conf import settings
from django.db import migrations


def create_existing_user_roles(apps, schema_editor):
    RoleProfile = apps.get_model("mrp", "RoleProfile")
    app_label, model_name = settings.AUTH_USER_MODEL.split(".")
    User = apps.get_model(app_label, model_name)
    profiles = [
        RoleProfile(
            user_id=user.pk,
            role="admin" if user.is_superuser else "manager",
        )
        for user in User.objects.all().iterator()
    ]
    RoleProfile.objects.bulk_create(profiles, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("mrp", "0005_material_material_unit_price_nonnegative_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(create_existing_user_roles, migrations.RunPython.noop),
    ]
