const webpack = require('webpack');
const path = require('path');
const {VueLoaderPlugin} = require('vue-loader');

const config = {
  entry: {
    basket: './topobank/assets/basket.js',
    topography_detail: './topobank/assets/topography_detail.js'
  },
  output: {
    path: path.resolve(__dirname, 'topobank/static/js'),
    filename: '[name].bundle.js'
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

module.exports = config;
