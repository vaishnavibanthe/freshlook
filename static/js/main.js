// Front-end Interactivity Scripts - ThinkArtha Redesign

document.addEventListener('DOMContentLoaded', () => {
    // 1. Sticky Header Shrink Effect
    const header = document.querySelector('.header');
    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            header.classList.add('shrunk');
        } else {
            header.classList.remove('shrunk');
        }
    });


    // 3. Tab Selectors
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.getAttribute('data-tab');
            const parent = btn.closest('.tabs-container');
            if (!parent) return;
            
            parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            parent.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
            
            btn.classList.add('active');
            const targetPane = parent.querySelector(`#${tabId}`);
            if (targetPane) {
                targetPane.classList.add('active');
            }
        });
    });

    // 4. Video Testimonials Lightbox Controller
    const playButtons = document.querySelectorAll('.video-play-btn, .webcast-play-trigger');
    const lightbox = document.createElement('div');
    lightbox.className = 'video-lightbox';
    lightbox.innerHTML = `
        <div class="lightbox-content" style="width: 100%; max-width: 800px; aspect-ratio: 16/9; background: transparent; padding: 0;">
            <button class="lightbox-close" style="z-index: 20;"><i class="fas fa-times"></i></button>
            <div class="lightbox-body" style="width:100%; height:100%; display:flex; align-items:center; justify-content:center;">
                <!-- Content dynamically injected -->
            </div>
        </div>
    `;
    document.body.appendChild(lightbox);

    const lightboxBody = lightbox.querySelector('.lightbox-body');
    const closeBtn = lightbox.querySelector('.lightbox-close');
    
    const closeLightbox = () => {
        lightbox.classList.remove('open');
        if (lightboxBody) lightboxBody.innerHTML = ''; // Stop video playback
    };

    if (closeBtn) {
        closeBtn.addEventListener('click', closeLightbox);
    }
    lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox) {
            closeLightbox();
        }
    });

    playButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const vimeoId = btn.getAttribute('data-vimeo-id');
            
            if (vimeoId) {
                // Play real Vimeo video in responsive iframe
                lightboxBody.innerHTML = `
                    <div style="position: relative; width: 100%; height: 100%; background: #000; border-radius: 12px; overflow: hidden; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);">
                        <iframe src="https://player.vimeo.com/video/${vimeoId}?autoplay=1" style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; border: 0;" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe>
                    </div>
                `;
            } else {
                // Fallback to mock preview layout
                const card = btn.closest('.video-card') || btn.closest('.webcast-banner') || btn.closest('.webcast-preview-banner');
                let title = "Streaming Resource";
                let desc = "Connecting to Artha Solutions media servers...";
                
                if (card) {
                    const titleEl = card.querySelector('.video-title, .webcast-title, .webcast-card-title');
                    const descEl = card.querySelector('.video-desc, .webcast-desc, .webcast-card-meta');
                    if (titleEl) title = titleEl.innerText;
                    if (descEl) desc = descEl.innerText;
                }
                
                lightboxBody.innerHTML = `
                    <div style="width:100%; height:100%; display:flex; flex-direction:column; align-items:center; justify-content:center; color:#fff; font-family:'Outfit',sans-serif; text-align:center; padding: 40px; background: radial-gradient(circle, #1e293b 0%, #0f172a 100%); border-radius: 12px;">
                        <i class="fas fa-play-circle" style="font-size: 80px; color: var(--accent-cyan); margin-bottom: 24px; animation: pulseGlow 2s infinite;"></i>
                        <h3 style="font-size:24px; margin-bottom:12px; font-weight:700;">${title}</h3>
                        <p style="color:var(--text-tertiary); max-width:480px; font-size:14px;">${desc}</p>
                        <div style="margin-top:32px; width:60px; height:3px; background:var(--grad-primary); border-radius:2px;"></div>
                    </div>
                `;
            }
            
            lightbox.classList.add('open');
        });
    });

    // 5. Scroll Counter Animation
    const counterElements = document.querySelectorAll('.stat-number');
    const runCounters = () => {
        counterElements.forEach(counter => {
            const targetStr = counter.getAttribute('data-target');
            if (!targetStr) return;
            const target = parseFloat(targetStr);
            const isPercent = targetStr.includes('%');
            const isMult = targetStr.includes('x') || targetStr.includes('×') || targetStr.includes('3×');
            
            let count = 0;
            const speed = 100;
            const increment = target / speed;
            
            const updateCount = () => {
                count += increment;
                if (count < target) {
                    if (isPercent) {
                        counter.innerText = Math.ceil(count) + '%';
                    } else if (isMult) {
                        counter.innerText = count.toFixed(1).replace('.0', '') + '×';
                    } else {
                        counter.innerText = Math.ceil(count);
                    }
                    setTimeout(updateCount, 15);
                } else {
                    counter.innerText = targetStr;
                }
            };
            updateCount();
        });
    };

    if (counterElements.length > 0) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    runCounters();
                    observer.disconnect();
                }
            });
        }, { threshold: 0.5 });
        const targetSec = document.querySelector('.stats-section');
        if (targetSec) observer.observe(targetSec);
    }

    // 6. FAQ Accordion Click Handlers
    const faqQuestions = document.querySelectorAll('.faq-question');
    faqQuestions.forEach(q => {
        q.addEventListener('click', () => {
            const item = q.closest('.faq-item');
            const isActive = item.classList.contains('active');
            
            document.querySelectorAll('.faq-item').forEach(i => {
                i.classList.remove('active');
                const ans = i.querySelector('.faq-answer');
                if (ans) ans.style.maxHeight = '0px';
            });
            
            if (!isActive) {
                item.classList.add('active');
                const ans = item.querySelector('.faq-answer');
                if (ans) ans.style.maxHeight = ans.scrollHeight + 'px';
            }
        });
    });

    // 7. Contact Form AJAX (mock submission)
    const contactForm = document.getElementById('artha-contact-form');
    if (contactForm) {
        contactForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const submitBtn = contactForm.querySelector('button[type="submit"]');
            const origBtnText = submitBtn.innerHTML;
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = 'Sending message <i class="fas fa-spinner fa-spin btn-icon"></i>';
            
            const formData = new FormData(contactForm);
            
            try {
                const response = await fetch('/contact-us', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.ok) {
                    const result = await response.json();
                    showToast(result.message);
                    contactForm.reset();
                } else {
                    showToast('An error occurred. Please try again later.');
                }
            } catch (err) {
                console.error(err);
                showToast('Unable to connect to server. Please check connection.');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = origBtnText;
            }
        });
    }

    function showToast(message) {
        let toast = document.querySelector('.toast-msg');
        if (!toast) {
            toast = document.createElement('div');
            toast.className = 'toast-msg';
            document.body.appendChild(toast);
        }
        toast.innerHTML = `<i class="fas fa-check-circle" style="margin-right: 8px;"></i> ${message}`;
        toast.classList.add('show');
        
        setTimeout(() => {
            toast.classList.remove('show');
        }, 5000);
    }

    // 8. Scroll Reveal Animations (fade and slide up)
    const revealElements = document.querySelectorAll('.card, .feature-split, .section-header, .testimonial-frame, .video-card, .webcast-banner, .ai-card');
    if (revealElements.length > 0) {
        revealElements.forEach(el => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(20px)';
            el.style.transition = 'opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1), transform 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
        });

        const revealObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                    revealObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.1 });

        revealElements.forEach(el => revealObserver.observe(el));
    }

    // 9. WordPress-style Admin Post Editor & AI SEO panel Logic
    const editorForm = document.getElementById('blog-editor-form');
    if (editorForm) {
        const titleInput = document.getElementById('post-title');
        const slugInput = document.getElementById('post-slug');
        const contentInput = document.getElementById('post-content');
        
        const keywordInput = document.getElementById('seo-focus-keyword');
        const metaTitleInput = document.getElementById('seo-meta-title-input');
        const metaDescInput = document.getElementById('seo-meta-desc-input');
        
        const titleCharCount = document.getElementById('title-char-count');
        const descCharCount = document.getElementById('desc-char-count');
        
        const titleProgressBar = document.getElementById('title-progress-bar');
        const descProgressBar = document.getElementById('desc-progress-bar');
        
        const seoScoreBadge = document.getElementById('seo-score-badge');
        const seoScoreHidden = document.getElementById('post-seo-score');
        
        const formMetaTitle = document.getElementById('post-meta-title');
        const formMetaDesc = document.getElementById('post-meta-desc');
        const formKeywords = document.getElementById('post-keywords');

        // Helper: slugify text
        const slugify = (text) => {
            return text.toLowerCase()
                .replace(/[^a-z0-9\s-]/g, '')
                .replace(/[\s-]+/g, '-')
                .replace(/^-+|-+$/g, '');
        };

        // Sync Title with URL Slug dynamically
        titleInput.addEventListener('input', () => {
            if (!slugInput.getAttribute('data-touched')) {
                slugInput.value = slugify(titleInput.value);
            }
            if (metaTitleInput.value === "" || !metaTitleInput.getAttribute('data-touched')) {
                metaTitleInput.value = titleInput.value;
            }
            runSeoCalculations();
        });

        slugInput.addEventListener('input', () => {
            slugInput.setAttribute('data-touched', 'true');
        });

        metaTitleInput.addEventListener('input', () => {
            metaTitleInput.setAttribute('data-touched', 'true');
            runSeoCalculations();
        });

        // Setup live calculations
        metaDescInput.addEventListener('input', runSeoCalculations);
        contentInput.addEventListener('input', runSeoCalculations);
        keywordInput.addEventListener('input', runSeoCalculations);

        // Checklist Items Dom hooks
        const chkTitle = document.getElementById('chk-title');
        const chkDesc = document.getElementById('chk-desc');
        const chkLength = document.getElementById('chk-length');
        const chkDensity = document.getElementById('chk-density');
        const chkMetaLen = document.getElementById('chk-meta-len');

        function runSeoCalculations() {
            const title = titleInput.value;
            const content = contentInput.value;
            const keyword = keywordInput.value.trim().toLowerCase();
            const metaTitle = metaTitleInput.value;
            const metaDesc = metaDescInput.value;

            // Character Counts
            const tLen = metaTitle.length;
            const dLen = metaDesc.length;

            titleCharCount.innerText = `${tLen} / 60 chars`;
            descCharCount.innerText = `${dLen} / 160 chars`;

            // Progress bar percentages and colors
            // Title target: 50-60
            const tPercent = Math.min((tLen / 60) * 100, 100);
            titleProgressBar.style.width = `${tPercent}%`;
            if (tLen >= 50 && tLen <= 60) {
                titleProgressBar.style.backgroundColor = '#16a34a'; // green
            } else if (tLen > 60) {
                titleProgressBar.style.backgroundColor = '#dc2626'; // red
            } else {
                titleProgressBar.style.backgroundColor = '#ea580c'; // orange
            }

            // Description target: 120-160
            const dPercent = Math.min((dLen / 160) * 100, 100);
            descProgressBar.style.width = `${dPercent}%`;
            if (dLen >= 120 && dLen <= 160) {
                descProgressBar.style.backgroundColor = '#16a34a'; // green
            } else if (dLen > 160) {
                descProgressBar.style.backgroundColor = '#dc2626'; // red
            } else {
                descProgressBar.style.backgroundColor = '#ea580c'; // orange
            }

            // Calculate Checklist metrics
            let score = 0;
            
            // Check 1: Keyword in Title
            const keywordInTitle = keyword && title.toLowerCase().includes(keyword);
            toggleChecklist(chkTitle, keywordInTitle);
            if (keywordInTitle) score += 20;

            // Check 2: Keyword in Meta Description
            const keywordInDesc = keyword && metaDesc.toLowerCase().includes(keyword);
            toggleChecklist(chkDesc, keywordInDesc);
            if (keywordInDesc) score += 20;

            // Check 3: Content Word Count (>300 words)
            const words = content.trim().split(/\s+/).filter(w => w.length > 0);
            const wordCount = words.length;
            const optimalLength = wordCount >= 300;
            toggleChecklist(chkLength, optimalLength);
            if (optimalLength) score += 20;

            // Check 4: Keyword Density (1% to 2.5%)
            let densityPass = false;
            if (keyword && wordCount > 0) {
                // Count occurrences
                const regex = new RegExp('\\b' + keyword + '\\b', 'gi');
                const matches = content.match(regex);
                const count = matches ? matches.length : 0;
                const density = (count / wordCount) * 100;
                densityPass = density >= 1.0 && density <= 2.5;
            }
            toggleChecklist(chkDensity, densityPass);
            if (densityPass) score += 20;

            // Check 5: Meta description length (120-160)
            const metaLenPass = dLen >= 120 && dLen <= 160;
            toggleChecklist(chkMetaLen, metaLenPass);
            if (metaLenPass) score += 20;

            // Update UI Score
            seoScoreBadge.innerText = score;
            seoScoreHidden.value = score;
            
            if (score >= 80) {
                seoScoreBadge.style.color = '#16a34a';
                seoScoreBadge.style.borderColor = '#16a34a';
            } else if (score >= 50) {
                seoScoreBadge.style.color = '#ea580c';
                seoScoreBadge.style.borderColor = '#ea580c';
            } else {
                seoScoreBadge.style.color = '#dc2626';
                seoScoreBadge.style.borderColor = '#dc2626';
            }

            // Sync hidden inputs for Form POST submission
            formMetaTitle.value = metaTitle;
            formMetaDesc.value = metaDesc;
            // Keywords list (focus keyword + generated keywords)
            formKeywords.value = keywordInput.value;
        }

        function toggleChecklist(liElement, isValid) {
            const icon = liElement.querySelector('i') || liElement.querySelector('svg');
            if (isValid) {
                liElement.className = 'chk-valid';
                if (icon) icon.className = 'fas fa-check-circle';
            } else {
                liElement.className = 'chk-invalid';
                if (icon) icon.className = 'far fa-circle';
            }
        }

        // AI Mock Operations: Meta Description Generator
        document.getElementById('btn-ai-meta').addEventListener('click', () => {
            const content = contentInput.value.trim();
            if (content.length === 0) {
                showToast('Please write some content first.');
                return;
            }

            // Simple AI summarizer: extracts first 150 chars of content text cleanly
            let clean = content.replace(/\n+/g, ' ');
            let summary = clean.substring(0, 147);
            if (content.length > 147) summary += '...';
            
            metaDescInput.value = summary;
            runSeoCalculations();
            showToast('AI suggested meta description applied!');
        });

        // AI Mock Operations: Focus Keyword Extractor
        document.getElementById('btn-ai-keywords').addEventListener('click', () => {
            const content = contentInput.value.trim();
            if (content.length === 0) {
                showToast('Please write some content first.');
                return;
            }

            // Simple Keyword Extractor: counts noun frequencies excluding common stop words
            const words = content.toLowerCase()
                .replace(/[^a-z\s]/g, '')
                .split(/\s+/)
                .filter(w => w.length > 4); // ignore short words

            const stopWords = ['about', 'other', 'their', 'there', 'would', 'could', 'should', 'which', 'these', 'under', 'while', 'first', 'after', 'using', 'integrated', 'across', 'management', 'solutions', 'platform', 'systems', 'enterprise', 'modern', 'digital'];
            
            const frequencies = {};
            words.forEach(w => {
                if (stopWords.includes(w)) return;
                frequencies[w] = (frequencies[w] || 0) + 1;
            });

            // Sort by frequency
            const sorted = Object.keys(frequencies).sort((a, b) => frequencies[b] - frequencies[a]);
            const topKeywords = sorted.slice(0, 3);

            if (topKeywords.length > 0) {
                keywordInput.value = topKeywords.join(', ');
                runSeoCalculations();
                showToast(`AI Keywords extracted: ${topKeywords.join(', ')}`);
            } else {
                showToast('Write more paragraphs to extract keywords.');
            }
        });

        // Run calculations immediately on load
        runSeoCalculations();
    }

    // 10. Homepage Banner Carousel Slider Controller
    const sliderSection = document.getElementById('home-hero-slider');
    if (sliderSection) {
        const slides = sliderSection.querySelectorAll('.slide');
        const dots = sliderSection.querySelectorAll('.slider-dot');
        const prevArrow = sliderSection.querySelector('.prev-slide');
        const nextArrow = sliderSection.querySelector('.next-slide');
        
        let currentSlide = 0;
        let slideInterval = null;
        const slideDuration = 7000;
        
        function showSlide(index) {
            slides.forEach((slide, i) => {
                if (i === index) {
                    slide.classList.add('active');
                } else {
                    slide.classList.remove('active');
                }
            });
            
            dots.forEach((dot, i) => {
                if (i === index) {
                    dot.classList.add('active');
                } else {
                    dot.classList.remove('active');
                }
            });
            
            // Lazy load Vimeo background video
            const activeSlide = slides[index];
            if (activeSlide) {
                const iframe = activeSlide.querySelector('iframe[data-vimeo-id]');
                if (iframe) {
                    const vimeoId = iframe.getAttribute('data-vimeo-id');
                    iframe.src = `https://player.vimeo.com/video/${vimeoId}?autoplay=1&loop=1&muted=1&background=1`;
                    iframe.removeAttribute('data-vimeo-id');
                }
            }
            
            currentSlide = index;
        }
        
        function nextSlide() {
            let nextIndex = (currentSlide + 1) % slides.length;
            showSlide(nextIndex);
        }
        
        function prevSlide() {
            let prevIndex = (currentSlide - 1 + slides.length) % slides.length;
            showSlide(prevIndex);
        }
        
        function startAutoplay() {
            stopAutoplay();
            slideInterval = setInterval(nextSlide, slideDuration);
        }
        
        function stopAutoplay() {
            if (slideInterval) {
                clearInterval(slideInterval);
                slideInterval = null;
            }
        }
        
        if (nextArrow) {
            nextArrow.addEventListener('click', () => {
                nextSlide();
                startAutoplay();
            });
        }
        
        if (prevArrow) {
            prevArrow.addEventListener('click', () => {
                prevSlide();
                startAutoplay();
            });
        }
        
        dots.forEach((dot, i) => {
            dot.addEventListener('click', () => {
                showSlide(i);
                startAutoplay();
            });
        });
        
        sliderSection.addEventListener('mouseenter', stopAutoplay);
        sliderSection.addEventListener('mouseleave', startAutoplay);
        
        // Initialize
        showSlide(0);
        startAutoplay();
    }

    // --- Dynamic Navigation & Search Overlay JS ---

    // 11. Scrolled Header Class
    const mainHeader = document.getElementById('main-header');
    if (mainHeader) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 20) {
                mainHeader.classList.add('scrolled');
            } else {
                mainHeader.classList.remove('scrolled');
            }
        });
    }

    // 12. Search Overlay Toggle & Autocomplete Suggestions
    const searchTriggerBtn = document.getElementById('search-trigger-btn');
    const searchOverlay = document.getElementById('search-overlay');
    const searchCloseBtn = document.getElementById('search-close');
    const searchBackdrop = document.getElementById('search-backdrop');
    const searchInput = document.getElementById('search-overlay-input');
    const dynamicSuggestionsSection = document.getElementById('dynamic-suggestions-section');
    const dynamicSuggestionsList = document.getElementById('dynamic-suggestions-list');

    function openSearch() {
        if (searchOverlay) {
            searchOverlay.classList.add('active');
            searchOverlay.setAttribute('aria-hidden', 'false');
            document.body.style.overflow = 'hidden';
            setTimeout(() => {
                if (searchInput) searchInput.focus();
            }, 100);
        }
    }

    function closeSearch() {
        if (searchOverlay) {
            searchOverlay.classList.remove('active');
            searchOverlay.setAttribute('aria-hidden', 'true');
            document.body.style.overflow = '';
        }
    }

    if (searchTriggerBtn) {
        searchTriggerBtn.addEventListener('click', openSearch);
    }
    if (searchCloseBtn) {
        searchCloseBtn.addEventListener('click', closeSearch);
    }
    if (searchBackdrop) {
        searchBackdrop.addEventListener('click', closeSearch);
    }

    // Autocomplete Suggestions API Binding (with 200ms debounce)
    let searchDebounceTimeout = null;
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            clearTimeout(searchDebounceTimeout);
            const query = searchInput.value.trim();

            if (query.length < 2) {
                if (dynamicSuggestionsSection) dynamicSuggestionsSection.style.display = 'none';
                return;
            }

            searchDebounceTimeout = setTimeout(async () => {
                try {
                    const response = await fetch(`/api/search/suggestions?q=${encodeURIComponent(query)}`);
                    if (response.ok) {
                        const suggestions = await response.json();
                        if (suggestions.length > 0 && dynamicSuggestionsList) {
                            dynamicSuggestionsList.innerHTML = '';
                            suggestions.forEach(item => {
                                const suggestionEl = document.createElement('a');
                                suggestionEl.className = 'suggestion-item-link';
                                suggestionEl.href = item.url;
                                suggestionEl.innerHTML = `
                                    <span>${item.title}</span>
                                    <span class="suggestion-item-type">${item.type}</span>
                                `;
                                dynamicSuggestionsList.appendChild(suggestionEl);
                            });
                            if (dynamicSuggestionsSection) dynamicSuggestionsSection.style.display = 'block';
                        } else {
                            if (dynamicSuggestionsSection) dynamicSuggestionsSection.style.display = 'none';
                        }
                    }
                } catch (err) {
                    console.error('Error fetching search suggestions:', err);
                }
            }, 200);
        });
    }

    // 13. Mobile Navigation Drawer & Accordions
    const navToggle = document.getElementById('nav-toggle');
    const mobileDrawer = document.getElementById('mobile-drawer');
    const mobileCloseBtn = document.getElementById('mobile-close');
    const mobileBackdrop = document.getElementById('mobile-backdrop');

    function openMobileDrawer() {
        if (mobileDrawer && navToggle) {
            mobileDrawer.classList.add('active');
            mobileDrawer.setAttribute('aria-hidden', 'false');
            navToggle.setAttribute('aria-expanded', 'true');
            navToggle.classList.add('open');
            document.body.style.overflow = 'hidden';
        }
    }

    function closeMobileDrawer() {
        if (mobileDrawer && navToggle) {
            mobileDrawer.classList.remove('active');
            mobileDrawer.setAttribute('aria-hidden', 'true');
            navToggle.setAttribute('aria-expanded', 'false');
            navToggle.classList.remove('open');
            document.body.style.overflow = '';
        }
    }

    if (navToggle) {
        navToggle.addEventListener('click', () => {
            if (mobileDrawer && mobileDrawer.classList.contains('active')) {
                closeMobileDrawer();
            } else {
                openMobileDrawer();
            }
        });
    }
    if (mobileCloseBtn) {
        mobileCloseBtn.addEventListener('click', closeMobileDrawer);
    }
    if (mobileBackdrop) {
        mobileBackdrop.addEventListener('click', closeMobileDrawer);
    }

    // Accordions inside Mobile Drawer
    const mobileAccordions = document.querySelectorAll('.mobile-accordion-toggle');
    mobileAccordions.forEach(btn => {
        btn.addEventListener('click', () => {
            const panel = btn.nextElementSibling;
            const expanded = btn.getAttribute('aria-expanded') === 'true';

            // Close all other panels first
            mobileAccordions.forEach(b => {
                if (b !== btn) {
                    b.setAttribute('aria-expanded', 'false');
                    const p = b.nextElementSibling;
                    if (p) p.style.maxHeight = '0px';
                }
            });

            // Toggle current panel
            btn.setAttribute('aria-expanded', !expanded);
            if (!expanded) {
                panel.style.maxHeight = panel.scrollHeight + 'px';
            } else {
                panel.style.maxHeight = '0px';
            }
        });
    });

    // 14. Keyboard Accessibility
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeSearch();
            closeMobileDrawer();
        }
    });

    // Accessibly handle Tab focus trapped within dropdown panels or overlay
    const desktopDropdowns = document.querySelectorAll('.nav-item.has-dropdown');
    desktopDropdowns.forEach(dropdown => {
        const rootLink = dropdown.querySelector('.nav-link');
        const megaPanel = dropdown.querySelector('.nav-mega-menu');
        if (rootLink && megaPanel) {
            rootLink.addEventListener('focus', () => {
                rootLink.setAttribute('aria-expanded', 'true');
            });
            // Close when focus leaves the parent container
            dropdown.addEventListener('focusout', (e) => {
                if (!dropdown.contains(e.relatedTarget)) {
                    rootLink.setAttribute('aria-expanded', 'false');
                }
            });
        }
    });
});
