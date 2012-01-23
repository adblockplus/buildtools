/*
 * This Source Code is subject to the terms of the Mozilla Public License
 * version 2.0 (the "License"). You can obtain a copy of the License at
 * http://mozilla.org/MPL/2.0/.
 */

const Cc = Components.classes;
const Ci = Components.interfaces;
const Cu = Components.utils;

Cu.import("resource://gre/modules/Services.jsm");
Cu.import("resource://gre/modules/XPCOMUtils.jsm");

exports.WindowObserver = WindowObserver;

/**
 * This class will call listener's method applyToWindow() for all new chrome
 * windows being opened. It will also call listener's method removeFromWindow()
 * for all windows still open when the extension is shut down.
 * @constructor
 */
function WindowObserver(/**Object*/ listener)
{
  this._listener  = listener;

  let e = Services.ww.getWindowEnumerator();
  while (e.hasMoreElements())
    this._listener.applyToWindow(e.getNext().QueryInterface(Ci.nsIDOMWindow));

  Services.ww.registerNotification(this);

  this._shutdownHandler = function()
  {
    let e = Services.ww.getWindowEnumerator();
    while (e.hasMoreElements())
      this._listener.removeFromWindow(e.getNext().QueryInterface(Ci.nsIDOMWindow));

    Services.ww.unregisterNotification(this);
  }.bind(this);
  onShutdown.add(this._shutdownHandler);
}
WindowObserver.prototype =
{
  _listener: null,
  _shutdownHandler: null,

  shutdown: function()
  {
    if (!this._shutdownHandler)
      return;

    onShutdown.remove(this._shutdownHandler);
    this._shutdownHandler();
    this._shutdownHandler = null;
  },

  observe: function(subject, topic, data)
  {
    if (topic == "domwindowopened")
    {
      let window = subject.QueryInterface(Ci.nsIDOMWindow);
      window.addEventListener("DOMContentLoaded", function()
      {
        if (this._shutdownHandler)
          this._listener.applyToWindow(window);
      }.bind(this), false);
    }
  },

  QueryInterface: XPCOMUtils.generateQI([Ci.nsISupportsWeakReference, Ci.nsIObserver])
};
