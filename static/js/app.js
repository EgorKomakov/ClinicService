const { createApp, ref, reactive, onMounted } = Vue;

createApp({
    setup() {
        const flashMessages = reactive([]);

        function addFlash(category, text) {
            flashMessages.push({ category, text });
            setTimeout(() => {
                const idx = flashMessages.findIndex(m => m.category === category && m.text === text);
                if (idx !== -1) flashMessages.splice(idx, 1);
            }, 5000);
        }
        function removeFlash(index) {
            flashMessages.splice(index, 1);
        }

        const feedback = reactive({
            fullname: '',
            phone: '',
            email: '',
            message: ''
        });
        const agreement = ref(false);
        const status = reactive({ type: '', text: '' });
        const loading = ref(false);
        const errors = reactive({ fullname: '', phone: '', email: '' });

        function filterPhone(event) {
            let value = event.target.value;
            value = value.replace(/[^\d\s+\-()]/g, '');
            feedback.phone = value;
            if (errors.phone) errors.phone = '';
        }

        function validateField(field) {
            if (field === 'fullname') {
                errors.fullname = feedback.fullname.trim().split(' ').length < 2 ? 'Введите фамилию и имя' : '';
            } else if (field === 'phone') {
                const digits = feedback.phone.replace(/\D/g, '');
                errors.phone = digits.length < 10 ? 'Минимум 10 цифр' : '';
            } else if (field === 'email') {
                errors.email = !feedback.email.includes('@') || !feedback.email.includes('.') ? 'Некорректный email' : '';
            }
        }

        function validateFeedback() {
            validateField('fullname');
            validateField('phone');
            validateField('email');
            return !errors.fullname && !errors.phone && !errors.email;
        }

        async function submitFeedback() {
            status.type = '';
            status.text = '';
            if (!validateFeedback()) return;
            if (!agreement.value) {
                status.type = 'danger';
                status.text = 'Необходимо согласие на обработку данных';
                return;
            }
            loading.value = true;
            try {
                const res = await fetch('/contacts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        fullname: feedback.fullname.trim(),
                        phone: feedback.phone.trim(),
                        email: feedback.email.trim(),
                        message: feedback.message.trim()
                    })
                });
                const data = await res.json();
                if (data.success) {
                    status.type = 'success';
                    status.text = data.message;
                    feedback.fullname = '';
                    feedback.phone = '';
                    feedback.email = '';
                    feedback.message = '';
                    agreement.value = false;
                    errors.fullname = '';
                    errors.phone = '';
                    errors.email = '';
                } else {
                    status.type = 'danger';
                    status.text = data.message || 'Ошибка отправки';
                }
            } catch (e) {
                status.type = 'danger';
                status.text = 'Ошибка соединения с сервером';
            } finally {
                loading.value = false;
            }
        }

        onMounted(() => {
            const path = window.location.pathname;
            document.querySelectorAll('.nav-link').forEach(link => {
                if (link.getAttribute('href') === path) {
                    link.classList.add('fw-bold');
                }
            });
        });

        return {
            flashMessages,
            addFlash,
            removeFlash,
            feedback,
            agreement,
            status,
            loading,
            errors,
            filterPhone,
            validateField,
            validateFeedback,
            submitFeedback
        };
    }
}).mount('#app');