document.addEventListener('DOMContentLoaded', function() {
    // Éléments DOM
    const chatWindow = document.getElementById('chatWindow');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const modeRadios = document.getElementsByName('responseMode');
    
    // Génération d'un ID utilisateur unique
    const userId = 'user_' + Math.random().toString(36).substr(2, 9);
    
    // Connexion Socket.IO
    const socket = io();
    
    // Gestion de la connexion
    socket.on('connect', function() {
        console.log('Connecté au serveur');
    });
    
    // Réception des messages
    socket.on('response', function(data) {
        // Suppression de l'indicateur de saisie si présent
        const typingIndicator = document.querySelector('.typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
        
        if (data.type === 'status') {
            // Message de statut, ajouter un indicateur de saisie
            addTypingIndicator();
        } else {
            // Message normal, ajouter au chat
            addBotMessage(data.message, data.blocks);
            
            // Scroll vers le bas
            chatWindow.scrollTop = chatWindow.scrollHeight;
        }
    });
    
    // Envoi de message quand le bouton est cliqué
    sendButton.addEventListener('click', sendMessage);
    
    // Envoi de message quand Entrée est pressé
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
    
    // Fonction d'envoi de message
    function sendMessage() {
        const message = messageInput.value.trim();
        if (!message) return;
        
        // Récupération du mode sélectionné
        let selectedMode = 'detail';
        for (const radio of modeRadios) {
            if (radio.checked) {
                selectedMode = radio.value;
                break;
            }
        }
        
        // Ajout du message utilisateur à l'interface
        addUserMessage(message);
        
        // Envoi du message au serveur
        socket.emit('message', {
            user_id: userId,
            message: message,
            mode: selectedMode
        });
        
        // Ajout d'un indicateur de saisie
        addTypingIndicator();
        
        // Réinitialisation de l'input
        messageInput.value = '';
        
        // Focus sur l'input
        messageInput.focus();
    }
    
    // Fonction pour ajouter un message utilisateur à l'interface
    function addUserMessage(text) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'user-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const messageP = document.createElement('p');
        messageP.textContent = text;
        
        contentDiv.appendChild(messageP);
        messageDiv.appendChild(contentDiv);
        
        const timeSpan = document.createElement('span');
        timeSpan.className = 'message-time';
        timeSpan.textContent = new Date().toLocaleTimeString();
        messageDiv.appendChild(timeSpan);
        
        chatWindow.appendChild(messageDiv);
        
        // Scroll vers le bas
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    
    // Fonction pour ajouter un message du bot à l'interface
    function addBotMessage(text, blocks) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'bot-message';
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        // Si des blocs sont présents, les traiter
        if (blocks && Array.isArray(blocks)) {
            blocks.forEach(block => {
                if (block.type === 'section' && block.text) {
                    const blockContent = document.createElement('div');
                    if (block.text.type === 'mrkdwn') {
                        // Utiliser marked.js pour convertir le markdown
                        blockContent.innerHTML = marked.parse(block.text.text);
                    } else {
                        blockContent.textContent = block.text.text;
                    }
                    contentDiv.appendChild(blockContent);
                } else if (block.type === 'divider') {
                    const divider = document.createElement('hr');
                    contentDiv.appendChild(divider);
                }
            });
        } else {
            // Fallback au texte simple si pas de blocs
            const messageContent = document.createElement('div');
            messageContent.innerHTML = marked.parse(text);
            contentDiv.appendChild(messageContent);
        }
        
        messageDiv.appendChild(contentDiv);
        
        const timeSpan = document.createElement('span');
        timeSpan.className = 'message-time';
        timeSpan.textContent = new Date().toLocaleTimeString();
        messageDiv.appendChild(timeSpan);
        
        chatWindow.appendChild(messageDiv);
        
        // Scroll vers le bas
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
    
    // Fonction pour ajouter un indicateur de saisie
    function addTypingIndicator() {
        // Suppression des indicateurs existants
        const existingIndicator = document.querySelector('.typing-indicator');
        if (existingIndicator) {
            existingIndicator.remove();
        }
        
        const indicator = document.createElement('div');
        indicator.className = 'typing-indicator';
        indicator.innerHTML = `
            <div class="message-content">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        
        chatWindow.appendChild(indicator);
        
        // Scroll vers le bas
        chatWindow.scrollTop = chatWindow.scrollHeight;
    }
});