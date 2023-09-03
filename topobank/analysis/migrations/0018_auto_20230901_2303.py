# Generated by Django 3.2.18 on 2023-09-01 21:03

from django.contrib.contenttypes.models import ContentType
from django.db import migrations, models
import django.db.models.deletion


def forward_func(apps, schema_editor):
    Analysis = apps.get_model('analysis', 'analysis')
    AnalysisSubject = apps.get_model('analysis', 'analysissubject')
    for analysis in Analysis.objects.all():
        # Get analysis subject from content type framework
        ct = ContentType.objects.get_for_id(analysis.subject_type.id)
        subject = ct.get_object_for_this_type(id=analysis.subject_id)
        surface = collection = topography = None
        if ct.name == 'surface':
            surface = subject.id
        elif ct.name == 'surfacecollection':
            collection = subject.id
        elif ct.name == 'topography':
            topography = subject.id
        else:
            raise ValueError(f'Cannot handle content type {ct.name}')
        # Create new AnalysisSubject for this analysis
        analysis.subj = AnalysisSubject.objects.create(surface_id=surface, collection_id=collection,
                                                       topography_id=topography)
        analysis.save()


def reverse_func(apps, schema_editor):
    Analysis = apps.get_model('analysis', 'analysis')
    for analysis in Analysis.objects.all():
        if analysis.subj.topography is not None:
            analysis.subject = analysis.subj.topography
        elif analysis.subj.surface is not None:
            analysis.subject = analysis.subj.surface
        elif analysis.subj.collection is not None:
            analysis.subject = analysis.subj.collection
        else:
            # Some database inconsistency occured.
            # We just drop this analysis.
            analysis.delete()
        analysis.save()


class Migration(migrations.Migration):
    dependencies = [
        ('manager', '0033_surfacecollection'),
        ('analysis', '0017_alter_analysis_kwargs'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnalysisSubject',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('collection', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                                 to='manager.surfacecollection')),
                ('surface', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                              to='manager.surface')),
                ('topography', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                                 to='manager.topography')),
            ],
        ),
        migrations.AddField(
            model_name='analysis',
            name='subj',
            field=models.OneToOneField(null=True, on_delete=django.db.models.deletion.PROTECT,
                                       to='analysis.analysissubject'),
        ),
        migrations.RunPython(
            forward_func,
            reverse_func
        ),
        migrations.RemoveField(
            model_name='analysis',
            name='subject_id',
        ),
        migrations.RemoveField(
            model_name='analysis',
            name='subject_type',
        ),
        migrations.RenameField(
            model_name='analysis',
            old_name='subj',
            new_name='subject',
        ),
    ]