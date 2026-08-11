pragma Singleton
import QtQuick

/*
 * Sound access for reusable components.
 *
 * Components in this module must not reach for the application's context
 * property directly: that couples them to a name defined elsewhere and breaks
 * the moment one is loaded without it. Main.qml assigns `backend` once at
 * startup and everything here degrades to silence if it never happens.
 */
QtObject {
    property var backend: null
    property bool muted: false

    function play(name) {
        if (backend && !muted)
            backend.playSound(name)
    }
}
