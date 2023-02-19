const webpack = require('webpack');
const path = require('path');
const {VueLoaderPlugin} = require('vue-loader');

module.exports = {
  entry: {
    base: './topobank/assets/base.js',
    select: './topobank/assets/select.js',
    topography_detail: './topobank/assets/topography_detail.js'
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
