# SECS/GEM demo view

A Perspective view that shows live status variables, the last wafer event,
alarm text, bridge health, and buttons that send remote commands.

## Install

Copy the folder into your Ignition project, so the path is:

    <ignition data>/projects/<YourProject>/com.inductiveautomation.perspective/views/SecsGemDemo/view.json

In Docker that is inside the gateway container volume. If the project folder is
bind mounted to your host, just drop it there. Then in the gateway web UI run a
project scan, or reopen the Designer.

## After opening

1. The tag paths assume the provider is named `MQTT Engine` and the namespace
   root is `fab/etch01`. If yours differ, select a value label and fix the tag
   path in the binding.
2. The trend chart is left unbound on purpose. Drag ChamberTemp and
   ChamberPressure onto it from the tag browser, which sets up the history
   query for you. Turn on tag history for those tags first.
3. The event cards read `event/WaferEnd/data/2001` and `2002`. If MQTT Engine
   nested those differently, browse the event folder and repoint them.

## The command buttons

Each button publishes JSON to `fab/etch01/cmd`:

    system.cirruslink.engine.publish("emqx", topic, payload, 1, False)

Check the argument order against your MQTT Engine version in the script console
first. If the function is unavailable, the fallback is to run the publish from a
gateway script using a plain MQTT client library, or to add a small REST
endpoint to the bridge.

## What success looks like

* The pill at top right reads true and turns green
* Pressure, temp and RF update every two seconds
* Pressing STOP drops state to IDLE and RF to zero within a second or two
* Pressing START resumes wafer cycles and the wafer count climbs

## Live flow diagram

The second component down is a Markdown component whose source is an expression
that builds an SVG string from the tags. It shows the tool, the bridge, EMQX and
Ignition with arrows between them, plus the dashed return path for remote
commands.

It reacts to live data:

* Tool box turns green while PROCESSING, gray when IDLE
* Bridge box turns green when the online tag is true, red when the last will fires
* Temperature, pressure, RF power and wafer count are printed in the boxes

Requirements: the Markdown component's `escapeHtml` property must stay false,
which is how it is set in the file. If your gateway blocks inline HTML in
Markdown, the fallback is to save `preview.svg` into the gateway's webserver
folder and use an Image component pointing at it, which loses the live colors.
