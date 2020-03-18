/* This Source Code Form is subject to the terms of the Mozilla Public
 * License, v. 2.0. If a copy of the MPL was not distributed with this
 * file, You can obtain one at http://mozilla.org/MPL/2.0/. */

"use strict";

const path = require("path");
const process = require("process");

const MemoryFS = require("memory-fs");
const webpack = require("webpack");

// We read the configuration from STDIN rather than as an argument to improve
// the output on error. Otherwise the (fairly huge) configuration is printed
// along with the actual error message.
let inputChunks = [];
process.stdin.setEncoding("utf-8");
process.stdin.on("data", chunk => { inputChunks.push(chunk); });
process.stdin.on("end", () =>
{
  let {bundles, extension_path,
       info_module, resolve_paths, aliases} = JSON.parse(inputChunks.join(""));

  // The contents of the info module is passed to us as a string from the Python
  // packager and we pass it through to our custom loader now so it is available
  // at bundle time.
  require("./info-loader").setInfoModule(info_module);

  // Since the cost of starting Node.js and loading all the modules is hugely
  // larger than actually producing bundles we avoid paying it multiple times,
  // instead producing all the bundles in one go.
  let options = [];
  for (let {bundle_name, entry_points} of bundles)
  {
    options.push({
      context: extension_path,
      module: {
        rules: [{
          include: path.join(__dirname, "info.js"),
          use: ["info-loader"]
        }]
      },
      entry: entry_points,
      output: {
        path: path.resolve(""),
        filename: bundle_name
      },
      node: {
        global: false
      },
      resolve: {
        modules: resolve_paths,
        alias: aliases,
        plugins: [
          function()
          {
            // Our old module system in packagerChrome.py used to prefix
            // module names with the name of their parent directory and an
            // underscore - but only when that directory wasn't called
            // "lib". This plugin is for backwards compatability, but can
            // be removed once use of that deprecated syntax has been
            // replaced.
            this.plugin("described-resolve", (request, callback) =>
            {
              let target = request.request;

              let prefixIndex = target.indexOf("_");
              if (prefixIndex == -1)
                return callback();

              let prefix = target.substring(0, prefixIndex);
              if (prefix == "lib")
                return callback();

              let fixedTarget = path.join(prefix,
                                           target.substring(prefixIndex + 1));
              return this.doResolve(
                "resolve", Object.assign({}, request, {request: fixedTarget}),
                "Changed prefixed path using legacy buildtools syntax from " +
                target + " to " + fixedTarget,
                callback
              );
            });
          }
        ]
      },
      resolveLoader: {
        modules: [path.resolve(__dirname)]
      }
    });
  }

  // Based on this example
  // https://webpack.js.org/api/node/#custom-file-systems
  let memoryFS = new MemoryFS();
  let webpackCompiler = webpack(options);

  webpackCompiler.outputFileSystem = memoryFS;
  webpackCompiler.run((err, stats) =>
  {
    // Error handling is based on this example
    // https://webpack.js.org/api/node/#error-handling
    if (err)
    {
      let reason = err.stack || err;
      if (err.details)
        reason += "\n" + err.details;
      throw new Error(reason);
    }
    else if (stats.hasErrors())
      throw new Error(stats.toJson().errors.join("\n"));
    else
    {
      let output = {};
      let files = output.files = {};

      for (let config of options)
      {
        let filepath = path.join(config.output.path, config.output.filename);
        let relativeFilepath = path.relative("", config.output.filename);
        files[relativeFilepath] = memoryFS.readFileSync(filepath, "utf-8");
      }

      // We provide a list of all the bundled files, so the packager can avoid
      // including them again outside of a bundle. Otherwise we end up including
      // duplicate copies in our builds.
      let included = new Set();
      for (let bundle of stats.toJson().children)
      {
        for (let chunk of bundle.chunks)
        {
          for (let module of chunk.modules)
          {
            if (!module.name.startsWith("multi "))
              included.add(path.relative(extension_path, module.name));
          }
        }
      }
      output.included = Array.from(included);

      console.log(JSON.stringify(output));
    }
  });
});
