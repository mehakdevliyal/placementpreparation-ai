/**
 * Speech-to-Text Recognition Module for Interview Assessment Sessions
 */
document.addEventListener('DOMContentLoaded', function () {
    const micBtn = document.getElementById('micBtn');
    const micIcon = document.getElementById('micIcon');
    const answerBox = document.getElementById('answerBox');
    const listeningTag = document.getElementById('listeningTag');

    if (!micBtn || !answerBox) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let isListening = false;

    if (!SpeechRecognition) {
        micBtn.style.display = 'none';
    } else {
        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = 'en-US';

        let finalTranscript = '';

        function setListeningState(state) {
            isListening = state;
            if (state) {
                micBtn.classList.add('listening');
                if (micIcon) micIcon.className = 'bi bi-mic-mute-fill';
                if (listeningTag) listeningTag.classList.add('active');
            } else {
                micBtn.classList.remove('listening');
                if (micIcon) micIcon.className = 'bi bi-mic-fill';
                if (listeningTag) listeningTag.classList.remove('active');
            }
        }

        function toggleMic() {
            if (!isListening) {
                finalTranscript = answerBox.value ? answerBox.value + ' ' : '';
                recognition.start();
            } else {
                recognition.stop();
            }
        }

        micBtn.addEventListener('click', toggleMic);

        recognition.onstart = function() {
            setListeningState(true);
        };

        recognition.onend = function() {
            setListeningState(false);
        };

        recognition.onresult = function(event) {
            let interimTranscript = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript + ' ';
                } else {
                    interimTranscript += transcript;
                }
            }
            answerBox.value = finalTranscript + interimTranscript;
        };

        recognition.onerror = function(event) {
            console.log('Speech recognition error:', event.error);
            setListeningState(false);
        };

        document.addEventListener('keydown', function(e) {
            if (e.code === 'Insert') {
                e.preventDefault();
                toggleMic();
            }
        });

        // Expose a global method to stop mic from other scripts
        window.stopSpeechRecognition = function() {
            if (isListening && recognition) {
                recognition.stop();
            }
        };
    }
});
