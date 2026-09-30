/**
 * Comportamento do painel de administração: política de resposta do HTMX, região de alertas,
 * destaque do item ativo nas listas e alternância do menu raiz.
 * Tudo fica neste arquivo para que a política de segurança de conteúdo dispense 'unsafe-inline'.
 */
(function () {
    "use strict";

    var UNEXPECTED_ERROR_MESSAGE = "Erro inesperado. Tente novamente.";
    var CONNECTION_ERROR_MESSAGE = "Não foi possível falar com o servidor. Verifique a conexão e tente novamente.";
    var INVALID_DATA_MESSAGE = "Dados inválidos. Verifique os campos e tente novamente.";
    var FALLBACK_MESSAGES = {
        403: "Você não tem permissão para realizar esta ação.",
        404: "O item solicitado não foi encontrado.",
        429: "Muitas tentativas. Aguarde um minuto e tente novamente."
    };
    var SERVER_ERROR_STATUS = 500;
    // Erros com corpo HTML montado pelo servidor: aparecem dentro do painel ou formulário de origem.
    var PANE_ERROR_STATUSES = [400, 401, 422, 429];

    function alertRegion() {
        return document.getElementById("page-alert");
    }

    function showAlert(message) {
        var region = alertRegion();
        if (!region) {
            return;
        }
        region.textContent = message;
        region.hidden = false;
    }

    function clearAlert() {
        var region = alertRegion();
        if (region) {
            region.textContent = "";
            region.hidden = true;
        }
    }

    function isHtmlResponse(xhr) {
        var contentType = xhr.getResponseHeader("Content-Type") || "";
        return contentType.indexOf("text/html") !== -1;
    }

    function serverDetail(xhr) {
        try {
            var detail = JSON.parse(xhr.responseText).detail;
            return typeof detail === "string" && detail ? detail : null;
        } catch (error) {
            return null;
        }
    }

    function alertMessageFor(xhr) {
        if (xhr.status >= SERVER_ERROR_STATUS) {
            return UNEXPECTED_ERROR_MESSAGE;
        }
        if (xhr.status === 400 || xhr.status === 422) {
            return INVALID_DATA_MESSAGE;
        }
        return serverDetail(xhr) || FALLBACK_MESSAGES[xhr.status] || UNEXPECTED_ERROR_MESSAGE;
    }

    function handleBeforeSwap(event) {
        var xhr = event.detail.xhr;
        if (xhr.status < 400) {
            return;
        }
        if (PANE_ERROR_STATUSES.indexOf(xhr.status) !== -1 && isHtmlResponse(xhr)) {
            event.detail.shouldSwap = true;
            event.detail.isError = false;
            return;
        }
        event.detail.shouldSwap = false;
        showAlert(alertMessageFor(xhr));
    }

    function currentEntityId() {
        var card = document.querySelector(".split-detail [data-entity-id]");
        return card ? card.getAttribute("data-entity-id") : null;
    }

    function highlightActiveItem() {
        var activeId = currentEntityId();
        document.querySelectorAll(".split-list-item").forEach(function (item) {
            var isActive = activeId !== null && item.getAttribute("data-id") === activeId;
            item.classList.toggle("active", isActive);
        });
    }

    function toggleParentSelector(checkbox) {
        var parentContainer = document.getElementById("parent-container");
        if (parentContainer) {
            parentContainer.classList.toggle("is-hidden", checkbox.checked);
        }
    }

    document.addEventListener("htmx:beforeRequest", clearAlert);
    document.addEventListener("htmx:beforeSwap", handleBeforeSwap);
    document.addEventListener("htmx:afterSwap", highlightActiveItem);
    document.addEventListener("htmx:sendError", function () {
        showAlert(CONNECTION_ERROR_MESSAGE);
    });
    document.addEventListener("htmx:timeout", function () {
        showAlert(CONNECTION_ERROR_MESSAGE);
    });
    document.addEventListener("change", function (event) {
        if (event.target && event.target.id === "is_root") {
            toggleParentSelector(event.target);
        }
    });
    document.addEventListener("DOMContentLoaded", highlightActiveItem);
})();
