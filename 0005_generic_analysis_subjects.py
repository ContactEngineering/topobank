

from django.db import migrations, models
import django.db.models.deletion
from django.contrib.contenttypes.models import ContentType

from django.apps.registry import apps as global_apps
from django.contrib.contenttypes.management import create_contenttypes

from topobank.manager.models import Topography


def replace_topography_by_subject(apps, schema_editor):
    """Saves analyses for topographies in generic field 'subject'.

    Afterwards, the column 'topography' can be deleted from
    Analysis Table.

    Parameters
    ----------
    apps
    schema_editor

    Returns
    -------
    None
    """
    Analysis = apps.get_model('analysis', 'Analysis')

    for a in Analysis.objects.all():
        a.subject_id = a.topography_id
        a.sub
        a.save()


def reverse_replace_topography_by_subject(apps, schema_editor):
    """Make that column 'topography' is used again instead of generic subject.

    All analyses which do not refer to topographies are deleted.

    Parameters
    ----------
    apps
    schema_editor

    Returns
    -------
    None
    """
    #analysis_app = global_apps.get_app_config('analysis')
    #create_contenttypes(analysis_app)

    Analysis = apps.get_model('analysis', 'Analysis')
    Topography = apps.get_model('manager', 'Topography')
    ContentType = apps.get_model('contenttypes', 'ContentType')


    analysis_ids_for_deletion = []

    for a in Analysis.objects.all():
        #print(a.subject_type)
        #print("DIR:\n", dir(a.subject_type))
        #subject_type = ContentType.objects.get_for_id(a.subject_type.id)

        #subject = subject_type.get_object_for_this_type(id=a.subject_id)

        #if isinstance(subject, Topography):
        a.topography_id = a.subject_id
        a.save()
        #else:
        #    analysis_ids_for_deletion.append(a.id)

    # Before migration to generic subjects, only analyses for topographies
    # can be saved. Therefore analyses for all other type of subjects are deleted.
    #Analysis.objects.filter(id__in=analysis_ids_for_deletion).delete()


# noinspection PyMissingOrEmptyDocstring
class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('analysis', '0004_auto_20191007_1135'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='analysisfunction',
            name='automatic',
        ),
        migrations.AlterField(
            model_name='analysisfunction',
            name='pyfunc',
            field=models.CharField(max_length=256, default='test', null=True),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='analysisfunction',
            name='pyfunc',
        ),
        migrations.AddField(
            model_name='analysisfunction',
            name='card_view_flavor',
            field=models.CharField(choices=[('simple', 'Simple display of the results as raw data structure'),
                                            ('plot', 'Display results in a plot with multiple datasets'),
                                            ('power spectrum', 'Display results in a plot suitable for power spectrum'),
                                            ('contact mechanics', 'Display suitable for contact mechanics including special widgets'),
                                            ('rms table', 'Display a table with RMS values.')],
                                   default='simple', max_length=50),
        ),
        migrations.CreateModel(
            name='AnalysisFunctionImplementation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_ref', models.CharField(help_text="name of Python function in 'topobank.analysis.functions' module",
                                              max_length=256)),
                ('function', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                               related_name='implementations',
                                               to='analysis.AnalysisFunction')),
                ('subject_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   to='contenttypes.ContentType')),
            ],
        ),
        migrations.AddConstraint(
            model_name='analysisfunctionimplementation',
            constraint=models.UniqueConstraint(fields=('function', 'subject_type'), name='distinct_implementation'),
        ),
        migrations.AddField(
            model_name='analysis',
            name='subject_id',
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='analysis',
            name='subject_type',
            field=models.ForeignKey(default=ContentType.objects.get_for_model(Topography).id,
                                    on_delete=django.db.models.deletion.CASCADE,
                                    to='contenttypes.ContentType'),
            preserve_default=False,
        ),
        migrations.RunPython(
            code=replace_topography_by_subject,
            reverse_code=reverse_replace_topography_by_subject
        ),
        #migrations.AlterField(
        #  model_name='analysis',
        #  name='topography',
        #  field=models.ForeignKey('manager.Topography', on_delete=models.CASCADE, default=2),
        #  preserve_default=False,
        #),
        #migrations.RemoveField(
        #    model_name='analysis',
        #    name='topography'
        #),
    ]

