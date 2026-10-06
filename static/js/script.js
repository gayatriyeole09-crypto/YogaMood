/* =====================================================
   YOGAMOOD JAVASCRIPT
===================================================== */


/* =====================================================
   MOOD SELECTION
===================================================== */

function selectMood(mood) {

    localStorage.setItem(
        "selectedMood",
        mood
    );

    window.location.href =
        "/yoga?mood=" +
        encodeURIComponent(mood);
}


function getSelectedMood() {

    return localStorage.getItem(
        "selectedMood"
    ) || "Stressed";

}


function clearSelectedMood() {

    localStorage.removeItem(
        "selectedMood"
    );

}


/* =====================================================
   PAGE LOAD
===================================================== */

document.addEventListener(
    "DOMContentLoaded",
    function () {


        /* ---------------------------------------------
           SPLASH SCREEN
        --------------------------------------------- */

        const splash =
            document.getElementById(
                "yogamoodSplash"
            );

        const omSound =
            document.getElementById(
                "omSound"
            );


        /* ---------------------------------------------
           OM SOUND
        --------------------------------------------- */

        if (omSound) {

            omSound.volume = 0.35;

            const playOm = function () {

                omSound.play()
                    .then(function () {

                        console.log(
                            "Om sound started."
                        );

                    })
                    .catch(function () {

                        console.log(
                            "Browser blocked autoplay."
                        );

                    });

            };


            /*
             * Try autoplay
             */

            playOm();


            /*
             * If browser blocks autoplay,
             * play after first user interaction.
             */

            document.addEventListener(
                "click",
                function () {

                    if (omSound.paused) {

                        playOm();

                    }

                },
                { once: true }
            );

        }


        /* ---------------------------------------------
           HIDE SPLASH
        --------------------------------------------- */

        if (splash) {

            setTimeout(
                function () {

                    splash.classList.add(
                        "hide"
                    );

                },
                2500
            );

        }


        /* ---------------------------------------------
           CONSOLE
        --------------------------------------------- */

        console.log(
            "YogaMood loaded successfully 🌿"
        );

    }
);