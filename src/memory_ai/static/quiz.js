/*
 * Client-side quiz navigation (ticket 12, issue #65).
 *
 * Per decisions.md #3, Next/Previous/Show Answer are pure client-side state
 * transitions over the question set already embedded in the page by the
 * "Quiz Me" response -- this file makes zero network calls of its own.
 *
 * The navigation-bounds helpers (`clampNext`/`clampPrev`/`isFirst`/`isLast`)
 * are exported as plain, DOM-free functions (decisions.md #5: no wraparound
 * past the first or last question) so they can be unit-tested directly under
 * Node without a browser -- see tests/test_quiz_nav_js.py.
 */
(function (root, factory) {
    if (typeof module === "object" && module.exports) {
        module.exports = factory();
    } else {
        root.MemoryAIQuiz = factory();
    }
})(typeof self !== "undefined" ? self : this, function () {
    "use strict";

    function isFirst(index) {
        return index === 0;
    }

    function isLast(index, length) {
        return index === length - 1;
    }

    // No wraparound: at the last question, "next" holds the index steady.
    function clampNext(index, length) {
        return isLast(index, length) ? index : index + 1;
    }

    // No wraparound: at the first question, "previous" holds the index steady.
    function clampPrev(index) {
        return isFirst(index) ? index : index - 1;
    }

    function init(sourceId) {
        var dataEl = document.getElementById("quiz-data-" + sourceId);
        var data = JSON.parse(dataEl.textContent);
        var index = 0;
        var answerShown = false;

        var questionEl = document.getElementById("quiz-question-" + sourceId);
        var answerEl = document.getElementById("quiz-answer-" + sourceId);
        var progressEl = document.getElementById("quiz-progress-" + sourceId);
        var showBtn = document.getElementById("quiz-show-answer-" + sourceId);
        var prevBtn = document.getElementById("quiz-prev-" + sourceId);
        var nextBtn = document.getElementById("quiz-next-" + sourceId);

        function render() {
            var current = data[index];
            questionEl.textContent = current.question;
            answerEl.textContent = current.answer;
            // Show Answer is per-question and resets on every navigation
            // (decisions.md #6): arriving at any question always starts
            // with its answer hidden.
            answerEl.hidden = !answerShown;
            progressEl.textContent = "Question " + (index + 1) + " of " + data.length;
            prevBtn.disabled = isFirst(index);
            nextBtn.disabled = isLast(index, data.length);
        }

        showBtn.addEventListener("click", function () {
            answerShown = true;
            render();
        });

        prevBtn.addEventListener("click", function () {
            if (isFirst(index)) {
                return;
            }
            index = clampPrev(index);
            answerShown = false;
            render();
        });

        nextBtn.addEventListener("click", function () {
            if (isLast(index, data.length)) {
                return;
            }
            index = clampNext(index, data.length);
            answerShown = false;
            render();
        });

        render();
    }

    return {
        init: init,
        clampNext: clampNext,
        clampPrev: clampPrev,
        isFirst: isFirst,
        isLast: isLast,
    };
});
