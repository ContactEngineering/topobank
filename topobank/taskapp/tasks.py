import numpy as np
import pickle

from .celery import app
from topobank.analysis.models import Analysis

def height_distribution(surface, bins=None):

    if bins is None:
        bins = int(np.sqrt(np.prod(surface.shape))+1.0)

    profile = surface.profile()

    mean_height = np.mean(profile)
    rms_height = surface.compute_rms_height()

    hist, bin_edges = np.histogram(np.ma.compressed(profile), bins=bins, normed=True)

    return {
        'mean_height': mean_height,
        'rms_height': rms_height,
        'hist': hist,
        'bin_edges': bin_edges,
    }

@app.task(bind=True, ignore_result=True)
def perform_analysis(self, topography_id, analysis_func, *args, **kwargs):
    #
    # create entry in Analysis table
    #
    analysis = Analysis.objects.create(
                                    topography_id=topography_id,
                                    task_id=self.request.id,
                                    args=pickle.dumps(args),
                                    kwargs=pickle.dumps(kwargs))

    #
    # perform analysis
    #
    try:
        result = analysis_func(*args, **kwargs)
        analysis.successful = True
    except Exception as exc:
        analysis.failed = True

    #
    # update entry with result
    #
    analysis.result = pickle.dumps(result)

    analysis.save()
