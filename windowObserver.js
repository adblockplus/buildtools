/*
 * This Source Code is subject to the terms of the Mozilla Public License
 * version 2.0 (the "License"). You can obtain a copy of the License at
 * http://mozilla.org/MPL/2.0/.
 */

Cu.import("resource://gre/modules/Services.jsm");
Cu.import("resource://gre/modules/XPCOMUtils.jsm");

exports.WindowObserver = WindowObserver;

/**
 * This class will call listener's method applyToWindow() for all new chrome
 * windows being opened. It will also call listener's method removeFromWindow()
 * for all windows still open when the extension is shut down.
 * @param {Object} listener
 * @param {String} [when]   when to execute applyToWindow(). "start" means immediately
 *                          when the window opens, "ready" when its contents are available
 *                          and "end" (default) means to wait until the "load" event.
 * @param {Boolean} [ignoreUnloads]   Do not work around bug 721319 by calling
 *                                    removeFromWindow() when the window unloads.
 * @constructor
 */
function WindowObserver(listener, when, ignoreUnloads)
{
  this._listener  = listener;
  this._when = when;

  if (ignoreUnloads)
    this._unloadHandler = null;
  else
  {
    // Ugly bug 721319 work-around
    this._unloadHandler = function(event)
    {
      this.removeFromWindow(event.target.defaultView);
    }.bind(this);
  }

  let e = Services.ww.getWindowEnumerator();
  while (e.hasMoreElements())
  {
    let window = e.getNext().QueryInterface(Ci.nsIDOMWindow);
    if (when == "start" || window.document.readyState == "complete")
      this.applyToWindow(window);
    else
      this.observe(window, "domwindowopened", null);
  }

  Services.ww.registerNotification(this);

  this._shutdownHandler = function()
  {
    let e = Services.ww.getWindowEnumerator();
    while (e.hasMoreElements())
      this.removeFromWindow(e.getNext().QueryInterface(Ci.nsIDOMWindow));

    Services.ww.unregisterNotification(this);
  }.bind(this);
  onShutdown.add(this._shutdownHandler);
}
WindowObserver.prototype =
{
  _listener: null,
  _when: null,
  _shutdownHandler: null,
  _unloadHandler: null,

  shutdown: function()
  {
    if (!this._shutdownHandler)
      return;

    onShutdown.remove(this._shutdownHandler);
    this._shutdownHandler();
    this._shutdownHandler = null;
  },

  applyToWindow: function(window)
  {
    if (this._unloadHandler)
      window.addEventListener("unload", this._unloadHandler, false);
    this._listener.applyToWindow(window);
  },

  removeFromWindow: function(window)
  {
    if (this._unloadHandler)
      window.removeEventListener("unload", this._unloadHandler, false);
    this._listener.removeFromWindow(window);
  },

  observe: function(subject, topic, data)
  {
    if (topic == "domwindowopened")
    {
      if (this._when == "start")
      {
        this.applyToWindow(window);
        return;
      }

      let window = subject.QueryInterface(Ci.nsIDOMWindow);
      let event = (this._when == "ready" ? "DOMContentLoaded" : "load");
      let listener = function()
      {
        window.removeEventListener(event, listener, false);
        if (this._shutdownHandler)
          this.applyToWindow(window);
      }.bind(this);
      window.addEventListener(event, listener, false);
    }
  },

  QueryInterface: XPCOMUtils.generateQI([Ci.nsISupportsWeakReference, Ci.nsIObserver])
};
