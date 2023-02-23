const webpack = require('webpack');
const path = require('path');
const {VueLoaderPlugin} = require('vue-loader');

module.exports = {
  entry: {
    base: './topobank/frontend/manager/base.js',
    select: './topobank/frontend/manager/select.js',
    dzi: './topobank/frontend/manager/dzi.js',
    series_card: './topobank/frontend/analysis/series_card.js'
  },
  output: {
    path: path.resolve(__dirname, 'topobank/static/js'),
    filename: '[name].bundle.js',
    library: ['topobank', '[name]']
  },
  module: {
    rules: [
      {
        test: /\.vue$/,
        loader: 'vue-loader'
      },
      {
        test: /\.css$/,
        use: [
          'vue-style-loader',
          'css-loader'
        ]
      },
      {
        test: /\.scss$/,
        use: [
          'vue-style-loader',
          'css-loader',
          'sass-loader'
        ]
      }
    ]
  },
  resolve: {
    extensions: [
      '.js',
      '.vue'
    ]
  },
  plugins: [
    new VueLoaderPlugin()
  ]
};
