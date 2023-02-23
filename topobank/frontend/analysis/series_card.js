import {createApp} from 'vue';
import PlotCard from './SeriesCard.vue';

export function createCardApp(el, props) {
    let app = createApp(PlotCard, props);
    app.mount(el);
    return app;
}
