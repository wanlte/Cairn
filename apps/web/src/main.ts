import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { library } from '@fortawesome/fontawesome-svg-core'
import { faGithub } from '@fortawesome/free-brands-svg-icons'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
import './styles/main.css'

library.add(faGithub)

createApp(App).component('font-awesome-icon', FontAwesomeIcon).use(router).mount('#app')
